// Hand-written JSON codec for the security directory stored inside .qpanel files.
// No third-party dependency: the schema is fixed and small, so a strict recursive-descent
// reader is enough. Unknown object keys are skipped for forward compatibility.
//
// Wire form: {"securities":[{"sec_id":"..","code":"..","name":"..","board":0,
//                            "list_date":20200101,"delist_date":0}, ...]}
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

#include "qcore/panel.h"

namespace qc {
namespace {

void append_json_string(std::string& out, const std::string& s) {
  out.push_back('"');
  for (const char raw : s) {
    const auto c = static_cast<unsigned char>(raw);
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\b': out += "\\b"; break;
      case '\f': out += "\\f"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20U) {
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
          out += buf;
        } else {
          out.push_back(raw);
        }
    }
  }
  out.push_back('"');
}

void append_json_int(std::string& out, int64_t v) { out += std::to_string(v); }

[[noreturn]] void fail(const std::string& message) {
  throw std::runtime_error("securities JSON: " + message);
}

class JsonReader {
 public:
  explicit JsonReader(std::string_view text) : text_(text) {}

  void skip_ws() {
    while (pos_ < text_.size()) {
      const char c = text_[pos_];
      if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
        ++pos_;
      } else {
        break;
      }
    }
  }

  bool eof() {
    skip_ws();
    return pos_ >= text_.size();
  }

  char peek() {
    skip_ws();
    return pos_ < text_.size() ? text_[pos_] : '\0';
  }

  void expect(char c) {
    skip_ws();
    if (pos_ >= text_.size() || text_[pos_] != c) {
      fail(std::string("expected '") + c + "' at byte " + std::to_string(pos_));
    }
    ++pos_;
  }

  std::string parse_string() {
    skip_ws();
    expect('"');
    std::string out;
    while (pos_ < text_.size()) {
      const char c = text_[pos_++];
      if (c == '"') return out;
      if (c != '\\') {
        if (static_cast<unsigned char>(c) < 0x20U) fail("raw control character in string");
        out.push_back(c);
        continue;
      }
      if (pos_ >= text_.size()) fail("unterminated escape");
      const char esc = text_[pos_++];
      switch (esc) {
        case '"': out.push_back('"'); break;
        case '\\': out.push_back('\\'); break;
        case '/': out.push_back('/'); break;
        case 'b': out.push_back('\b'); break;
        case 'f': out.push_back('\f'); break;
        case 'n': out.push_back('\n'); break;
        case 'r': out.push_back('\r'); break;
        case 't': out.push_back('\t'); break;
        case 'u': append_unicode(out); break;
        default: fail(std::string("invalid escape '\\") + esc + "'");
      }
    }
    fail("unterminated string");
  }

  int64_t parse_int() {
    skip_ws();
    const std::size_t start = pos_;
    bool negative = false;
    if (pos_ < text_.size() && text_[pos_] == '-') {
      negative = true;
      ++pos_;
    }
    std::uint64_t magnitude = 0;
    std::size_t digits = 0;
    while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') {
      const auto digit = static_cast<std::uint64_t>(text_[pos_] - '0');
      if (magnitude > (UINT64_MAX - digit) / 10) fail("integer overflow");
      magnitude = magnitude * 10 + digit;
      ++pos_;
      ++digits;
    }
    if (digits == 0) fail("expected integer at byte " + std::to_string(start));
    if (negative) {
      if (magnitude > static_cast<std::uint64_t>(INT64_MAX) + 1U) fail("integer underflow");
      return magnitude == static_cast<std::uint64_t>(INT64_MAX) + 1U
                 ? INT64_MIN
                 : -static_cast<int64_t>(magnitude);
    }
    if (magnitude > static_cast<std::uint64_t>(INT64_MAX)) fail("integer overflow");
    return static_cast<int64_t>(magnitude);
  }

  // Skips any JSON value; used for unknown keys and metadata that the reader does not own.
  void skip_value() {
    const char c = peek();
    if (c == '"') {
      (void)parse_string();
      return;
    }
    if (c == '{') {
      expect('{');
      if (peek() == '}') {
        expect('}');
        return;
      }
      for (;;) {
        (void)parse_string();
        expect(':');
        skip_value();
        if (peek() == ',') {
          expect(',');
          continue;
        }
        expect('}');
        return;
      }
    }
    if (c == '[') {
      expect('[');
      if (peek() == ']') {
        expect(']');
        return;
      }
      for (;;) {
        skip_value();
        if (peek() == ',') {
          expect(',');
          continue;
        }
        expect(']');
        return;
      }
    }
    if (c == 't') {
      expect_literal("true");
      return;
    }
    if (c == 'f') {
      expect_literal("false");
      return;
    }
    if (c == 'n') {
      expect_literal("null");
      return;
    }
    skip_number();
  }

 private:
  // Skips a number token (integer or floating point); unknown values are not interpreted.
  void skip_number() {
    skip_ws();
    const std::size_t start = pos_;
    if (pos_ < text_.size() && (text_[pos_] == '-' || text_[pos_] == '+')) ++pos_;
    bool saw_digit = false;
    while (pos_ < text_.size()) {
      const char c = text_[pos_];
      if (c >= '0' && c <= '9') {
        saw_digit = true;
        ++pos_;
      } else if (c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-') {
        ++pos_;
      } else {
        break;
      }
    }
    if (!saw_digit || pos_ == start) fail("expected number at byte " + std::to_string(start));
  }

  void expect_literal(const char* literal) {
    for (const char* p = literal; *p != '\0'; ++p) {
      if (pos_ >= text_.size() || text_[pos_] != *p) fail(std::string("expected '") + literal + "'");
      ++pos_;
    }
  }

  static int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  }

  uint32_t parse_hex4() {
    if (pos_ + 4 > text_.size()) fail("truncated \\u escape");
    uint32_t value = 0;
    for (int i = 0; i < 4; ++i) {
      const int h = hex_value(text_[pos_ + static_cast<std::size_t>(i)]);
      if (h < 0) fail("invalid \\u escape");
      value = value * 16 + static_cast<uint32_t>(h);
    }
    pos_ += 4;
    return value;
  }

  static void append_utf8(std::string& out, uint32_t cp) {
    if (cp <= 0x7FU) {
      out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FFU) {
      out.push_back(static_cast<char>(0xC0U | (cp >> 6)));
      out.push_back(static_cast<char>(0x80U | (cp & 0x3FU)));
    } else if (cp <= 0xFFFFU) {
      out.push_back(static_cast<char>(0xE0U | (cp >> 12)));
      out.push_back(static_cast<char>(0x80U | ((cp >> 6) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | (cp & 0x3FU)));
    } else {
      out.push_back(static_cast<char>(0xF0U | (cp >> 18)));
      out.push_back(static_cast<char>(0x80U | ((cp >> 12) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | ((cp >> 6) & 0x3FU)));
      out.push_back(static_cast<char>(0x80U | (cp & 0x3FU)));
    }
  }

  void append_unicode(std::string& out) {
    uint32_t cp = parse_hex4();
    if (cp >= 0xD800U && cp <= 0xDBFFU) {  // high surrogate, expect \uDC00-\uDFFF
      if (pos_ + 2 > text_.size() || text_[pos_] != '\\' || text_[pos_ + 1] != 'u') {
        fail("unpaired high surrogate");
      }
      pos_ += 2;
      const uint32_t low = parse_hex4();
      if (low < 0xDC00U || low > 0xDFFFU) fail("invalid low surrogate");
      cp = 0x10000U + ((cp - 0xD800U) << 10) + (low - 0xDC00U);
    } else if (cp >= 0xDC00U && cp <= 0xDFFFU) {
      fail("unpaired low surrogate");
    }
    append_utf8(out, cp);
  }

  std::string_view text_;
  std::size_t pos_ = 0;
};

Security parse_security_object(JsonReader& reader) {
  Security sec;
  bool has_sec_id = false;
  bool has_code = false;
  reader.expect('{');
  if (reader.peek() != '}') {
    for (;;) {
      const std::string key = reader.parse_string();
      reader.expect(':');
      if (key == "sec_id") {
        sec.sec_id = reader.parse_string();
        has_sec_id = true;
      } else if (key == "code") {
        sec.code = reader.parse_string();
        has_code = true;
      } else if (key == "name") {
        sec.name = reader.parse_string();
      } else if (key == "board") {
        const int64_t board = reader.parse_int();
        if (board < 0 || board > 3) fail("board must be 0..3");
        sec.board = static_cast<int32_t>(board);
      } else if (key == "list_date") {
        const int64_t date = reader.parse_int();
        if (date < INT32_MIN || date > INT32_MAX) fail("list_date out of int32 range");
        sec.list_date = static_cast<Date>(date);
      } else if (key == "delist_date") {
        const int64_t date = reader.parse_int();
        if (date < INT32_MIN || date > INT32_MAX) fail("delist_date out of int32 range");
        sec.delist_date = static_cast<Date>(date);
      } else {
        reader.skip_value();
      }
      if (reader.peek() == ',') {
        reader.expect(',');
        continue;
      }
      break;
    }
  }
  reader.expect('}');
  if (!has_sec_id || sec.sec_id.empty()) fail("security object missing non-empty sec_id");
  if (!has_code || sec.code.empty()) fail("security object missing non-empty code");
  if (sec.list_date != kInvalidDate && !valid_date(sec.list_date)) fail("invalid list_date");
  if (sec.delist_date != kInvalidDate && !valid_date(sec.delist_date)) fail("invalid delist_date");
  if (sec.list_date != kInvalidDate && sec.delist_date != kInvalidDate &&
      sec.delist_date < sec.list_date) {
    fail("delist_date precedes list_date for security '" + sec.sec_id + "'");
  }
  return sec;
}

std::vector<Security> parse_security_array(JsonReader& reader) {
  std::vector<Security> out;
  reader.expect('[');
  if (reader.peek() != ']') {
    for (;;) {
      out.push_back(parse_security_object(reader));
      if (reader.peek() == ',') {
        reader.expect(',');
        continue;
      }
      break;
    }
  }
  reader.expect(']');
  return out;
}

}  // namespace

std::string securities_to_json(const std::vector<Security>& secs) {
  std::string out;
  out.reserve(secs.size() * 96 + 32);
  out += "{\"securities\":[";
  for (std::size_t i = 0; i < secs.size(); ++i) {
    if (i != 0) out.push_back(',');
    const Security& sec = secs[i];
    out += "{\"sec_id\":";
    append_json_string(out, sec.sec_id);
    out += ",\"code\":";
    append_json_string(out, sec.code);
    out += ",\"name\":";
    append_json_string(out, sec.name);
    out += ",\"board\":";
    append_json_int(out, sec.board);
    out += ",\"list_date\":";
    append_json_int(out, sec.list_date);
    out += ",\"delist_date\":";
    append_json_int(out, sec.delist_date);
    out.push_back('}');
  }
  out += "]}";
  return out;
}

std::vector<Security> securities_from_json(const std::string& json) {
  JsonReader reader(json);
  if (reader.eof()) fail("empty document");
  std::vector<Security> secs;
  if (reader.peek() == '[') {
    secs = parse_security_array(reader);
  } else {
    reader.expect('{');
    bool found = false;
    if (reader.peek() != '}') {
      for (;;) {
        const std::string key = reader.parse_string();
        reader.expect(':');
        if (key == "securities") {
          if (found) fail("duplicate 'securities' key");
          secs = parse_security_array(reader);
          found = true;
        } else {
          reader.skip_value();
        }
        if (reader.peek() == ',') {
          reader.expect(',');
          continue;
        }
        break;
      }
    }
    reader.expect('}');
    if (!found) fail("missing 'securities' array");
  }
  if (!reader.eof()) fail("trailing characters after document");
  std::unordered_set<std::string> ids;
  ids.reserve(secs.size() * 2 + 8);
  for (const Security& sec : secs) {
    if (!ids.insert(sec.sec_id).second) fail("duplicate sec_id '" + sec.sec_id + "'");
  }
  return secs;
}

}  // namespace qc
