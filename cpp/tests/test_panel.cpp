// .qpanel format: writer/reader roundtrip (both layouts), header layout, content hash and
// rejection of corrupted files. Magic/version/offsets are checked against the documented v1
// binary layout in cpp/src/panel/panel_format.h.
#include <catch2/catch_test_macros.hpp>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <utility>
#include <vector>

#include "qcore/panel.h"
#include "qcore/types.h"

namespace {

std::string temp_path(const char* tag) {
  static std::atomic<int> counter{0};
  const auto stamp =
      static_cast<long long>(std::chrono::steady_clock::now().time_since_epoch().count());
  return (std::filesystem::temp_directory_path() /
          (std::string("qcore_test_") + tag + "_" + std::to_string(stamp) + "_" +
           std::to_string(counter.fetch_add(1)) + ".qpanel"))
      .string();
}

struct TempFile {
  std::string path;
  ~TempFile() {
    std::error_code ec;
    std::filesystem::remove(path, ec);
  }
};

std::vector<qc::Security> make_securities() {
  return {{"S1", "600000", "浦发银行", 0, 19991110, 0},
          {"S2", "000001", "平安银行", 0, 19910403, 0},
          {"S3", "300750", "宁德时代", 1, 20180611, 0}};
}

std::vector<qc::Date> make_dates() {
  return {20200102, 20200103, 20200106, 20200107};
}

std::vector<double> make_st(size_t n_sec, size_t n_time) {
  std::vector<double> data(n_sec * n_time);
  for (size_t s = 0; s < n_sec; ++s) {
    for (size_t t = 0; t < n_time; ++t)
      data[s * n_time + t] = static_cast<double>(s * 100 + t) + 0.5;
  }
  return data;
}

std::vector<double> make_ts(size_t n_sec, size_t n_time) {
  std::vector<double> data(n_sec * n_time);
  for (size_t t = 0; t < n_time; ++t) {
    for (size_t s = 0; s < n_sec; ++s)
      data[t * n_sec + s] = 1000.0 + static_cast<double>(s * 10 + t);
  }
  return data;
}

std::vector<char> read_all(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  REQUIRE(in.good());
  return std::vector<char>(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

void write_all(const std::string& path, const std::vector<char>& bytes) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  REQUIRE(out.good());
  out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void patch_byte(const std::string& path, std::streamoff offset, unsigned char value) {
  std::fstream file(path, std::ios::binary | std::ios::in | std::ios::out);
  REQUIRE(file.good());
  file.seekp(offset);
  file.put(static_cast<char>(value));
  REQUIRE(file.good());
}

std::uint32_t get_u32(const std::vector<char>& bytes, std::size_t offset) {
  std::uint32_t value = 0;
  for (int i = 0; i < 4; ++i) {
    value |= static_cast<std::uint32_t>(static_cast<unsigned char>(bytes[offset + i])) << (8 * i);
  }
  return value;
}

std::uint64_t get_u64(const std::vector<char>& bytes, std::size_t offset) {
  std::uint64_t value = 0;
  for (int i = 0; i < 8; ++i) {
    value |= static_cast<std::uint64_t>(static_cast<unsigned char>(bytes[offset + i])) << (8 * i);
  }
  return value;
}

// Writes the standard 3 x 4 panel and returns the path (caller owns the TempFile).
void write_standard(const std::string& path, std::string metadata = "{\"source\":\"test\"}") {
  const auto secs = make_securities();
  const auto dates = make_dates();
  const auto st = make_st(secs.size(), dates.size());
  const auto ts = make_ts(secs.size(), dates.size());
  qc::PanelWriter writer(secs.size(), dates.size(), dates, secs);
  writer.add_field("close", qc::Layout::SecTime, st.data());
  writer.add_field("volume", qc::Layout::TimeSec, ts.data());
  writer.set_metadata(std::move(metadata));
  writer.write(path);
}

}  // namespace

TEST_CASE("panel roundtrip keeps values, layout, dates and securities", "[panel]") {
  const TempFile file{temp_path("roundtrip")};
  write_standard(file.path);
  CHECK(std::filesystem::file_size(file.path) % 64 == 0);
  qc::Panel panel = qc::Panel::open(file.path);
  CHECK(panel.n_sec() == 3);
  CHECK(panel.n_time() == 4);
  CHECK(panel.dates() == make_dates());
  REQUIRE(panel.securities().size() == 3);
  CHECK(panel.securities()[0].sec_id == "S1");
  CHECK(panel.securities()[0].name == "浦发银行");
  CHECK(panel.securities()[2].board == 1);
  CHECK(panel.securities()[2].list_date == 20180611);
  CHECK(panel.metadata_json() == "{\"source\":\"test\"}");
  CHECK((panel.field_names() == std::vector<std::string>{"close", "volume"}));
  CHECK(panel.has_field("close"));
  CHECK(!panel.has_field("amount"));
  const qc::FieldView close = panel.field("close");
  const qc::FieldView volume = panel.field("volume");
  CHECK(close.layout == qc::Layout::SecTime);
  CHECK(volume.layout == qc::Layout::TimeSec);
  const auto st = make_st(3, 4);
  const auto ts = make_ts(3, 4);
  for (size_t s = 0; s < 3; ++s) {
    for (size_t t = 0; t < 4; ++t) {
      CHECK(close.at(s, t) == st[s * 4 + t]);
      CHECK(volume.at(s, t) == ts[t * 3 + s]);
    }
  }
  // Columns are 64-byte aligned inside the mapping.
  CHECK(reinterpret_cast<std::uintptr_t>(close.data) % 64 == 0);
  CHECK(reinterpret_cast<std::uintptr_t>(volume.data) % 64 == 0);
  CHECK_THROWS_AS(panel.field("amount"), std::runtime_error);
  CHECK_NOTHROW(qc::Panel::validate(file.path));
  const qc::Panel verified = qc::Panel::open(file.path, /*verify_content=*/true);
  CHECK(verified.content_hash() == panel.content_hash());
  CHECK(verified.field("close").at(0, 0) == panel.field("close").at(0, 0));
}

TEST_CASE("panel header matches the documented v1 layout", "[panel][format]") {
  const TempFile file{temp_path("header")};
  write_standard(file.path);
  const auto bytes = read_all(file.path);
  REQUIRE(bytes.size() >= 256);
  CHECK(std::memcmp(bytes.data(), "QPANEL", 6) == 0);
  CHECK(get_u32(bytes, 8) == 1);     // version
  CHECK(get_u32(bytes, 12) == 256);  // header size
  CHECK(get_u32(bytes, 16) == 0);    // flags
  CHECK(get_u32(bytes, 20) == 2);    // field count
  CHECK(get_u64(bytes, 24) == bytes.size());
  CHECK(get_u64(bytes, 32) == 3);  // n_sec
  CHECK(get_u64(bytes, 40) == 4);  // n_time
  const std::uint64_t sec_offset = get_u64(bytes, 56);
  const std::uint64_t sec_size = get_u64(bytes, 64);
  const std::uint64_t meta_offset = get_u64(bytes, 72);
  const std::uint64_t dates_offset = get_u64(bytes, 88);
  const std::uint64_t dates_size = get_u64(bytes, 96);
  const std::uint64_t table_offset = get_u64(bytes, 104);
  const std::uint64_t table_size = get_u64(bytes, 112);
  const std::uint64_t data_offset = get_u64(bytes, 120);
  CHECK(sec_offset == 256);
  CHECK(sec_size == qc::securities_to_json(make_securities()).size());
  CHECK(meta_offset % 64 == 0);
  CHECK(dates_offset % 64 == 0);
  CHECK(table_offset % 64 == 0);
  CHECK(data_offset % 64 == 0);
  CHECK(dates_size == 4 * 4);
  CHECK(table_size == 2 * 64);
  CHECK(data_offset == ((table_offset + table_size + 63) / 64) * 64);
  // Content hash covers the payload exactly.
  const auto hash = qc::fnv1a64(bytes.data() + 256, bytes.size() - 256);
  CHECK(hash == get_u64(bytes, 48));
  CHECK(hash == qc::Panel::open(file.path).content_hash());
}

TEST_CASE("content hash is deterministic and data sensitive", "[panel][hash]") {
  const TempFile a{temp_path("hash_a")};
  const TempFile b{temp_path("hash_b")};
  write_standard(a.path);
  write_standard(b.path);
  const qc::Panel panel_a = qc::Panel::open(a.path);
  const qc::Panel panel_b = qc::Panel::open(b.path);
  CHECK(panel_a.content_hash() == panel_b.content_hash());
  // Same size, one changed payload byte: the fast path trusts the snapshot (it maps the
  // file as-is) but the content hash catches it, so verified open / validate must reject.
  // Patch a byte inside the first field column (past all structural sections).
  const auto bytes_b = read_all(b.path);
  const std::streamoff column = static_cast<std::streamoff>(get_u64(bytes_b, 120)) + 8;
  patch_byte(b.path, column, 0x7F);
  CHECK_NOTHROW(qc::Panel::open(b.path));
  CHECK_THROWS_AS(qc::Panel::open(b.path, /*verify_content=*/true), std::runtime_error);
  CHECK_THROWS_AS(qc::Panel::validate(b.path), std::runtime_error);
  // Metadata participates in the hash.
  const TempFile c{temp_path("hash_c")};
  write_standard(c.path, "{\"source\":\"other\"}");
  CHECK(qc::Panel::open(c.path).content_hash() != panel_a.content_hash());
}

TEST_CASE("corrupted panels are rejected instead of trusted", "[panel][corrupt]") {
  const TempFile base{temp_path("corrupt_base")};
  write_standard(base.path);
  const auto valid = read_all(base.path);

  const TempFile tiny{temp_path("corrupt_tiny")};
  write_all(tiny.path, std::vector<char>(100, '\0'));
  CHECK_THROWS_AS(qc::Panel::open(tiny.path), std::runtime_error);

  const TempFile empty_file{temp_path("corrupt_empty")};
  write_all(empty_file.path, std::vector<char>{});
  CHECK_THROWS_AS(qc::Panel::open(empty_file.path), std::runtime_error);
  CHECK_THROWS_AS(qc::Panel::open(temp_path("corrupt_missing")), std::runtime_error);
  CHECK_THROWS_AS(qc::Panel::validate(temp_path("corrupt_missing")), std::runtime_error);

  const TempFile bad_magic{temp_path("corrupt_magic")};
  auto bytes = valid;
  bytes[0] = 'X';
  write_all(bad_magic.path, bytes);
  CHECK_THROWS_AS(qc::Panel::open(bad_magic.path), std::runtime_error);

  const TempFile bad_version{temp_path("corrupt_version")};
  bytes = valid;
  bytes[8] = 9;
  write_all(bad_version.path, bytes);
  CHECK_THROWS_AS(qc::Panel::open(bad_version.path), std::runtime_error);

  const TempFile bad_header_size{temp_path("corrupt_hsize")};
  bytes = valid;
  bytes[12] = 64;
  write_all(bad_header_size.path, bytes);
  CHECK_THROWS_AS(qc::Panel::open(bad_header_size.path), std::runtime_error);

  const TempFile bad_flags{temp_path("corrupt_flags")};
  bytes = valid;
  bytes[16] = 1;
  write_all(bad_flags.path, bytes);
  CHECK_THROWS_AS(qc::Panel::open(bad_flags.path), std::runtime_error);

  const TempFile truncated{temp_path("corrupt_truncated")};
  write_all(truncated.path, std::vector<char>(valid.begin(), valid.end() - 1));
  CHECK_THROWS_AS(qc::Panel::open(truncated.path), std::runtime_error);

  const TempFile payload{temp_path("corrupt_payload")};
  bytes = valid;
  {
    const auto column = static_cast<std::size_t>(get_u64(valid, 120)) + 8;
    REQUIRE(column < bytes.size());
    bytes[column] = static_cast<char>(bytes[column] ^ 0x01);
  }
  write_all(payload.path, bytes);
  CHECK_NOTHROW(qc::Panel::open(payload.path));  // fast path does not hash the payload
  CHECK_THROWS_AS(qc::Panel::open(payload.path, /*verify_content=*/true), std::runtime_error);
  CHECK_THROWS_AS(qc::Panel::validate(payload.path), std::runtime_error);

  const TempFile bad_hash{temp_path("corrupt_hash")};
  bytes = valid;
  bytes[48] = static_cast<char>(bytes[48] ^ 0xFF);
  write_all(bad_hash.path, bytes);
  CHECK_NOTHROW(qc::Panel::open(bad_hash.path));
  CHECK_THROWS_AS(qc::Panel::open(bad_hash.path, /*verify_content=*/true), std::runtime_error);
  CHECK_THROWS_AS(qc::Panel::validate(bad_hash.path), std::runtime_error);

  const TempFile bad_offsets{temp_path("corrupt_offsets")};
  bytes = valid;
  bytes[120] = 65;  // data offset no longer 64B aligned / canonical
  write_all(bad_offsets.path, bytes);
  CHECK_THROWS_AS(qc::Panel::open(bad_offsets.path), std::runtime_error);
}

TEST_CASE("writer validates inputs", "[panel][validation]") {
  const auto secs = make_securities();
  const auto dates = make_dates();
  const auto data = make_st(secs.size(), dates.size());
  CHECK_THROWS_AS(qc::PanelWriter(0, 4, dates, secs), std::invalid_argument);
  CHECK_THROWS_AS(qc::PanelWriter(3, 0, dates, secs), std::invalid_argument);
  CHECK_THROWS_AS(qc::PanelWriter(3, 3, dates, secs), std::invalid_argument);
  CHECK_THROWS_AS(qc::PanelWriter(2, 4, dates, secs), std::invalid_argument);
  auto bad_dates = dates;
  std::swap(bad_dates[1], bad_dates[2]);
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, bad_dates, secs), std::invalid_argument);
  auto duplicated = dates;
  duplicated[1] = duplicated[0];
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, duplicated, secs), std::invalid_argument);
  auto invalid_dates = dates;
  invalid_dates[0] = 20200230;
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, invalid_dates, secs), std::invalid_argument);
  auto bad_securities = secs;
  bad_securities[1].sec_id = "S1";
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, dates, bad_securities), std::invalid_argument);
  bad_securities = secs;
  bad_securities[2].board = 9;
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, dates, bad_securities), std::invalid_argument);
  bad_securities = secs;
  bad_securities[0].sec_id.clear();
  CHECK_THROWS_AS(qc::PanelWriter(3, 4, dates, bad_securities), std::invalid_argument);

  qc::PanelWriter writer(3, 4, dates, secs);
  CHECK_THROWS_AS(writer.add_field("", qc::Layout::SecTime, data.data()), std::invalid_argument);
  CHECK_THROWS_AS(writer.add_field(std::string(32, 'x'), qc::Layout::SecTime, data.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(writer.add_field("close", qc::Layout::SecTime, nullptr), std::invalid_argument);
  CHECK_THROWS_AS(writer.add_field("close", static_cast<qc::Layout>(7), data.data()),
                  std::invalid_argument);
  writer.add_field("close", qc::Layout::SecTime, data.data());
  CHECK_THROWS_AS(writer.add_field("close", qc::Layout::SecTime, data.data()),
                  std::invalid_argument);
  CHECK_THROWS_AS(writer.set_metadata(""), std::invalid_argument);
  writer.set_metadata("{}");
  CHECK_THROWS_AS(
      writer.write(
          (std::filesystem::temp_directory_path() / "qcore_no_such_dir" / "panel.qpanel").string()),
      std::runtime_error);
}

TEST_CASE("panel with no fields is valid but empty", "[panel]") {
  const TempFile file{temp_path("no_fields")};
  const auto secs = make_securities();
  const auto dates = make_dates();
  qc::PanelWriter writer(secs.size(), dates.size(), dates, secs);
  writer.write(file.path);
  qc::Panel panel = qc::Panel::open(file.path);
  CHECK(panel.n_sec() == 3);
  CHECK(panel.n_time() == 4);
  CHECK(panel.field_names().empty());
  CHECK(!panel.has_field("close"));
  CHECK(panel.metadata_json() == "{}");  // default metadata
}

TEST_CASE("security directory JSON roundtrip and rejection", "[panel][json]") {
  std::vector<qc::Security> secs = make_securities();
  secs[0].name = "quote:\" backslash:\\ newline:\n tab:\t control:\x01 中文";
  const std::string json = qc::securities_to_json(secs);
  CHECK(json.rfind("{\"securities\":[", 0) == 0);
  const std::vector<qc::Security> parsed = qc::securities_from_json(json);
  REQUIRE(parsed.size() == secs.size());
  CHECK(parsed[0].sec_id == secs[0].sec_id);
  CHECK(parsed[0].code == secs[0].code);
  CHECK(parsed[0].name == secs[0].name);
  CHECK(parsed[1].list_date == secs[1].list_date);
  CHECK(parsed[2].board == secs[2].board);
  // Top-level array form and \u escapes are accepted.
  const std::vector<qc::Security> from_array = qc::securities_from_json(
      "[{\"sec_id\":\"\\u4e2d\\u6587\",\"code\":\"000001\",\"extra\":[1,2.5,null,true]}]");
  REQUIRE(from_array.size() == 1);
  CHECK(from_array[0].sec_id == "中文");
  CHECK(from_array[0].code == "000001");
  CHECK(from_array[0].board == 0);
  const char* bad[] = {
      "",
      "{}",
      "{\"securities\":[{\"sec_id\":\"a\"}]}",
      "{\"securities\":[{\"sec_id\":\"a\",\"code\":\"b\",\"board\":9}]}",
      "{\"securities\":[{\"sec_id\":\"a\",\"code\":\"b\",\"list_date\":20200230}]}",
      "{\"securities\":[{\"sec_id\":\"a\",\"code\":\"b\"},{\"sec_id\":\"a\",\"code\":\"c\"}]}",
      "{\"securities\":[{\"sec_id\":\"a\",\"code\":\"b\"}]} trailing",
      "{\"securities\":[{\"sec_id\":\"a\",\"code\":\"b\"}",
      "{\"securities\":[{\"sec_id\":\"\\ud800\",\"code\":\"b\"}]}",
  };
  for (const char* text : bad) {
    CHECK_THROWS_AS(qc::securities_from_json(text), std::runtime_error);
  }
}

TEST_CASE("panel move construction and assignment keep the mapping alive", "[panel]") {
  const TempFile file{temp_path("move")};
  write_standard(file.path);
  qc::Panel original = qc::Panel::open(file.path);
  qc::Panel moved = std::move(original);
  CHECK(moved.n_sec() == 3);
  CHECK(moved.field("close").at(2, 3) == make_st(3, 4)[2 * 4 + 3]);
  qc::Panel assigned = qc::Panel::open(file.path);
  assigned = std::move(moved);
  CHECK(assigned.n_sec() == 3);
  CHECK(assigned.field("volume").at(0, 0) == make_ts(3, 4)[0]);
}

#ifdef _WIN32
TEST_CASE("writer refuses to overwrite an existing panel on Windows", "[panel][windows]") {
  const TempFile file{temp_path("win_overwrite")};
  write_standard(file.path);
  CHECK_THROWS_AS(write_standard(file.path), std::runtime_error);
}
#else
TEST_CASE("writer atomically replaces an existing panel on POSIX", "[panel][posix]") {
  const TempFile file{temp_path("overwrite")};
  write_standard(file.path);
  const std::uint64_t first_hash = qc::Panel::open(file.path).content_hash();
  write_standard(file.path, "{\"source\":\"second\"}");
  CHECK(qc::Panel::open(file.path).metadata_json() == "{\"source\":\"second\"}");
  CHECK(qc::Panel::open(file.path).content_hash() != first_hash);
}
#endif
