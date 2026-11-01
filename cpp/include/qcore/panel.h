#pragma once
// .qpanel: immutable, 64B-aligned columnar panel for the C++ engine.
// Layout: header | security metadata (JSON) | dates (int32) | field table | field columns (double).
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include "qcore/types.h"

namespace qc {
enum class Layout : uint32_t { SecTime = 0, TimeSec = 1 };

struct Security {
  std::string sec_id;
  std::string code;
  std::string name;
  int32_t board = 0;  // 0 MAIN, 1 GEM, 2 STAR, 3 BSE
  Date list_date = kInvalidDate;
  Date delist_date = kInvalidDate;
};

struct FieldDesc {
  std::string name;
  Layout layout = Layout::SecTime;
  uint32_t elem_size = 8;
  uint64_t offset = 0;  // absolute file offset
  uint64_t count = 0;   // n_sec * n_time
};

struct FieldView {
  const double* data = nullptr;
  Layout layout = Layout::SecTime;
  size_t n_sec = 0;
  size_t n_time = 0;
  double at(size_t sec, size_t time) const {
    return layout == Layout::SecTime ? data[sec * n_time + time] : data[time * n_sec + sec];
  }
};

class PanelWriter {
 public:
  PanelWriter(size_t n_sec, size_t n_time, std::vector<Date> dates, std::vector<Security> securities);
  // data is row-major according to layout; copied into the file.
  void add_field(const std::string& name, Layout layout, const double* data);
  void set_metadata(const std::string& json);
  void write(const std::string& path);
  size_t n_sec() const { return n_sec_; }
  size_t n_time() const { return n_time_; }
 private:
  size_t n_sec_, n_time_;
  std::vector<Date> dates_;
  std::vector<Security> secs_;
  std::vector<FieldDesc> fields_;
  std::vector<std::vector<double>> buffers_;
  std::string metadata_ = "{}";
};

class Panel {
 public:
  static Panel open(const std::string& path);
  static void validate(const std::string& path);
  ~Panel();
  Panel(Panel&&) noexcept;
  Panel& operator=(Panel&&) noexcept;
  Panel(const Panel&) = delete;
  Panel& operator=(const Panel&) = delete;
  size_t n_sec() const { return n_sec_; }
  size_t n_time() const { return n_time_; }
  const std::vector<Date>& dates() const { return dates_; }
  const std::vector<Security>& securities() const { return securities_; }
  const std::string& metadata_json() const { return metadata_; }
  uint64_t content_hash() const { return content_hash_; }
  std::vector<std::string> field_names() const;
  bool has_field(const std::string& name) const { return fields_.count(name) > 0; }
  FieldView field(const std::string& name) const;
  const void* data() const { return map_; }
  size_t file_size() const { return file_size_; }
 private:
  Panel() = default;
  void* map_ = nullptr;
  size_t file_size_ = 0;
  size_t n_sec_ = 0, n_time_ = 0;
  uint64_t content_hash_ = 0;
  std::string metadata_;
  std::vector<Date> dates_;
  std::vector<Security> securities_;
  std::unordered_map<std::string, FieldDesc> fields_;
};

// Convert security metadata vector <-> JSON (small hand-written encoder, no dependencies).
std::string securities_to_json(const std::vector<Security>& secs);
std::vector<Security> securities_from_json(const std::string& json);
}  // namespace qc
