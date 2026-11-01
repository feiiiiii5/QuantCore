#include "expr_internal.h"

#include <cctype>
#include <cerrno>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace qc::expr {
namespace {

[[noreturn]] void lex_fail(size_t pos, const std::string& what) {
  throw std::invalid_argument("expression parse error at position " + std::to_string(pos + 1) +
                              ": " + what);
}

bool is_ident_start(char c) {
  const unsigned char u = static_cast<unsigned char>(c);
  return std::isalpha(u) != 0 || c == '_';
}

bool is_ident_char(char c) {
  const unsigned char u = static_cast<unsigned char>(c);
  return std::isalnum(u) != 0 || c == '_';
}

bool is_digit(char c) { return std::isdigit(static_cast<unsigned char>(c)) != 0; }

Token make(TokenKind kind, std::string text, size_t pos, double number = 0.0) {
  Token token;
  token.kind = kind;
  token.text = std::move(text);
  token.number = number;
  token.pos = pos;
  return token;
}

// Scan a number literal: digits with an optional fraction and an optional exponent.
// A leading '.' is accepted when followed by a digit (".5").
Token scan_number(const std::string& src, size_t& index) {
  const size_t n = src.size();
  const size_t start = index;
  if (src[index] == '.') {
    ++index;
    while (index < n && is_digit(src[index])) ++index;
  } else {
    while (index < n && is_digit(src[index])) ++index;
    if (index < n && src[index] == '.') {
      ++index;
      while (index < n && is_digit(src[index])) ++index;
    }
  }
  if (index < n && (src[index] == 'e' || src[index] == 'E')) {
    ++index;
    if (index < n && (src[index] == '+' || src[index] == '-')) ++index;
    if (index >= n || !is_digit(src[index])) lex_fail(start, "malformed number literal");
    while (index < n && is_digit(src[index])) ++index;
  }
  const std::string text = src.substr(start, index - start);
  errno = 0;
  char* end = nullptr;
  const double value = std::strtod(text.c_str(), &end);
  if (end == nullptr || *end != '\0') lex_fail(start, "malformed number literal '" + text + "'");
  if (errno == ERANGE) lex_fail(start, "number literal out of range: '" + text + "'");
  return make(TokenKind::Number, text, start, value);
}

}  // namespace

std::vector<Token> tokenize(const std::string& source) {
  std::vector<Token> tokens;
  const size_t n = source.size();
  size_t i = 0;
  while (i < n) {
    const char c = source[i];
    if (std::isspace(static_cast<unsigned char>(c)) != 0) {
      ++i;
      continue;
    }
    if (is_digit(c) || (c == '.' && i + 1 < n && is_digit(source[i + 1]))) {
      tokens.push_back(scan_number(source, i));
      continue;
    }
    if (is_ident_start(c)) {
      const size_t start = i;
      while (i < n && is_ident_char(source[i])) ++i;
      const std::string text = source.substr(start, i - start);
      if (text == "and") {
        tokens.push_back(make(TokenKind::And, text, start));
      } else if (text == "or") {
        tokens.push_back(make(TokenKind::Or, text, start));
      } else if (text == "not") {
        tokens.push_back(make(TokenKind::Not, text, start));
      } else {
        tokens.push_back(make(TokenKind::Identifier, text, start));
      }
      continue;
    }
    const size_t start = i;
    switch (c) {
      case '(':
        tokens.push_back(make(TokenKind::LParen, "(", start));
        ++i;
        break;
      case ')':
        tokens.push_back(make(TokenKind::RParen, ")", start));
        ++i;
        break;
      case ',':
        tokens.push_back(make(TokenKind::Comma, ",", start));
        ++i;
        break;
      case '+':
        tokens.push_back(make(TokenKind::Plus, "+", start));
        ++i;
        break;
      case '-':
        tokens.push_back(make(TokenKind::Minus, "-", start));
        ++i;
        break;
      case '*':
        tokens.push_back(make(TokenKind::Star, "*", start));
        ++i;
        break;
      case '/':
        tokens.push_back(make(TokenKind::Slash, "/", start));
        ++i;
        break;
      case '<':
        if (i + 1 < n && source[i + 1] == '=') {
          tokens.push_back(make(TokenKind::Le, "<=", start));
          i += 2;
        } else {
          tokens.push_back(make(TokenKind::Lt, "<", start));
          ++i;
        }
        break;
      case '>':
        if (i + 1 < n && source[i + 1] == '=') {
          tokens.push_back(make(TokenKind::Ge, ">=", start));
          i += 2;
        } else {
          tokens.push_back(make(TokenKind::Gt, ">", start));
          ++i;
        }
        break;
      case '=':
        if (i + 1 < n && source[i + 1] == '=') {
          tokens.push_back(make(TokenKind::Eq, "==", start));
          i += 2;
        } else {
          lex_fail(start, "unexpected '=' (use '==' for equality)");
        }
        break;
      case '!':
        if (i + 1 < n && source[i + 1] == '=') {
          tokens.push_back(make(TokenKind::Ne, "!=", start));
          i += 2;
        } else {
          tokens.push_back(make(TokenKind::Not, "!", start));
          ++i;
        }
        break;
      case '&':
        if (i + 1 < n && source[i + 1] == '&') {
          tokens.push_back(make(TokenKind::And, "&&", start));
          i += 2;
        } else {
          lex_fail(start, "unexpected '&' (use '&&' or 'and')");
        }
        break;
      case '|':
        if (i + 1 < n && source[i + 1] == '|') {
          tokens.push_back(make(TokenKind::Or, "||", start));
          i += 2;
        } else {
          lex_fail(start, "unexpected '|' (use '||' or 'or')");
        }
        break;
      default: {
        std::string what = "unexpected character '";
        if (std::isprint(static_cast<unsigned char>(c)) != 0) {
          what += c;
        } else {
          what += "\\x";
          const char* hex = "0123456789abcdef";
          const unsigned char u = static_cast<unsigned char>(c);
          what += hex[u >> 4];
          what += hex[u & 0x0Fu];
        }
        what += "'";
        lex_fail(start, what);
      }
    }
  }
  tokens.push_back(make(TokenKind::End, "<end>", n));
  return tokens;
}

std::string token_desc(const Token& token) {
  switch (token.kind) {
    case TokenKind::End:
      return "end of expression";
    case TokenKind::Number:
      return "number '" + token.text + "'";
    case TokenKind::Identifier:
      return "identifier '" + token.text + "'";
    default:
      return "'" + token.text + "'";
  }
}

}  // namespace qc::expr
