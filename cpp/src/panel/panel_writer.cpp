// PanelWriter: copies panel data into the immutable .qpanel v1 container.
// On-disk layout is documented in panel_format.h. The file is built at a temporary path
// and atomically renamed into place (POSIX). On Windows an existing target is refused
// (ADR-004: an update is a new snapshot; a mapped file must never be overwritten).
#include "qcore/panel.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#endif

#include "panel_format.h"

namespace qc {
namespace {

using panel_format::align_up;
using panel_format::FieldEntry;
using panel_format::Header;
using panel_format::kAlignment;
using panel_format::kFieldEntrySize;
using panel_format::kHeaderSize;
using panel_format::kMaxFieldName;

long process_id() {
#ifdef _WIN32
  return static_cast<long>(_getpid());
#else
  return static_cast<long>(::getpid());
#endif
}

void validate_dates(const std::vector<Date>& dates) {
  for (std::size_t i = 0; i < dates.size(); ++i) {
    if (!valid_date(dates[i])) {
      throw std::invalid_argument("PanelWriter: invalid date " + std::to_string(dates[i]) +
                                  " at time row " + std::to_string(i));
    }
    if (i > 0 && dates[i] <= dates[i - 1]) {
      throw std::invalid_argument("PanelWriter: dates must be strictly increasing (row " +
                                  std::to_string(i) + ")");
    }
  }
}

void validate_securities(const std::vector<Security>& secs) {
  std::unordered_set<std::string> seen;
  seen.reserve(secs.size() * 2 + 8);
  for (std::size_t i = 0; i < secs.size(); ++i) {
    const Security& sec = secs[i];
    if (sec.sec_id.empty()) {
      throw std::invalid_argument("PanelWriter: security " + std::to_string(i) +
                                  " has an empty sec_id");
    }
    if (sec.code.empty()) {
      throw std::invalid_argument("PanelWriter: security '" + sec.sec_id + "' has an empty code");
    }
    if (sec.board < 0 || sec.board > 3) {
      throw std::invalid_argument("PanelWriter: security '" + sec.sec_id +
                                  "' has board outside 0..3");
    }
    if (sec.list_date != kInvalidDate && !valid_date(sec.list_date)) {
      throw std::invalid_argument("PanelWriter: security '" + sec.sec_id +
                                  "' has an invalid list_date");
    }
    if (sec.delist_date != kInvalidDate && !valid_date(sec.delist_date)) {
      throw std::invalid_argument("PanelWriter: security '" + sec.sec_id +
                                  "' has an invalid delist_date");
    }
    if (sec.list_date != kInvalidDate && sec.delist_date != kInvalidDate &&
        sec.delist_date < sec.list_date) {
      throw std::invalid_argument("PanelWriter: security '" + sec.sec_id +
                                  "' has delist_date before list_date");
    }
    if (!seen.insert(sec.sec_id).second) {
      throw std::invalid_argument("PanelWriter: duplicate sec_id '" + sec.sec_id + "'");
    }
  }
}

// Sequential writer that keeps the running content hash over everything after the header.
class HashSink {
 public:
  // The stream position is already kHeaderSize (the placeholder header was written);
  // the hash covers exactly the payload bytes [kHeaderSize, file_size).
  explicit HashSink(std::ofstream& out) : out_(out), offset_(kHeaderSize) {}

  void write_bytes(const void* data, std::size_t n) {
    out_.write(static_cast<const char*>(data), static_cast<std::streamsize>(n));
    if (!out_)
      throw std::runtime_error("PanelWriter::write: short write to temporary file");
    // Hash starts from the qc::fnv1a64 default seed (obtained with a zero-length update).
    hash_ = fnv1a64(data, n, hash_);
    offset_ += n;
  }

  void write_zeros(uint64_t n) {
    static const std::array<char, kAlignment> kZeros{};
    while (n > 0) {
      const std::size_t chunk = static_cast<std::size_t>(std::min<uint64_t>(n, kZeros.size()));
      write_bytes(kZeros.data(), chunk);
      n -= chunk;
    }
  }

  void pad_to(uint64_t target) {
    if (offset_ > target)
      throw std::runtime_error("PanelWriter: internal layout overflow");
    write_zeros(target - offset_);
  }

  uint64_t hash() const {
    return hash_;
  }
  uint64_t offset() const {
    return offset_;
  }

 private:
  std::ofstream& out_;
  uint64_t hash_ = fnv1a64(nullptr, 0);
  uint64_t offset_ = kHeaderSize;
};

}  // namespace

PanelWriter::PanelWriter(size_t n_sec, size_t n_time, std::vector<Date> dates,
                         std::vector<Security> securities)
    : n_sec_(n_sec), n_time_(n_time), dates_(std::move(dates)), secs_(std::move(securities)) {
  if (n_sec_ == 0 || n_time_ == 0) {
    throw std::invalid_argument("PanelWriter: n_sec and n_time must be positive");
  }
  if (n_time_ != 0 && n_sec_ > std::numeric_limits<std::size_t>::max() / n_time_) {
    throw std::invalid_argument("PanelWriter: n_sec * n_time overflows size_t");
  }
  const std::size_t cells = n_sec_ * n_time_;
  if (cells > (std::numeric_limits<std::size_t>::max() - 4 * kAlignment) / sizeof(double)) {
    throw std::invalid_argument("PanelWriter: n_sec * n_time is too large to serialize");
  }
  if (dates_.size() != n_time_) {
    throw std::invalid_argument("PanelWriter: dates.size() (" + std::to_string(dates_.size()) +
                                ") must equal n_time (" + std::to_string(n_time_) + ")");
  }
  if (secs_.size() != n_sec_) {
    throw std::invalid_argument("PanelWriter: securities.size() (" + std::to_string(secs_.size()) +
                                ") must equal n_sec (" + std::to_string(n_sec_) + ")");
  }
  validate_dates(dates_);
  validate_securities(secs_);
}

void PanelWriter::add_field(const std::string& name, Layout layout, const double* data) {
  if (name.empty())
    throw std::invalid_argument("PanelWriter::add_field: empty field name");
  if (name.size() > kMaxFieldName) {
    throw std::invalid_argument("PanelWriter::add_field: field name '" + name +
                                "' exceeds 31 bytes");
  }
  if (name.find('\0') != std::string::npos) {
    throw std::invalid_argument("PanelWriter::add_field: field name contains NUL");
  }
  if (layout != Layout::SecTime && layout != Layout::TimeSec) {
    throw std::invalid_argument("PanelWriter::add_field: unsupported layout for '" + name + "'");
  }
  if (data == nullptr) {
    throw std::invalid_argument("PanelWriter::add_field: null data for '" + name + "'");
  }
  for (const FieldDesc& existing : fields_) {
    if (existing.name == name) {
      throw std::invalid_argument("PanelWriter::add_field: duplicate field '" + name + "'");
    }
  }
  const std::size_t count = n_sec_ * n_time_;
  FieldDesc desc;
  desc.name = name;
  desc.layout = layout;
  desc.elem_size = static_cast<uint32_t>(sizeof(double));
  desc.offset = 0;
  desc.count = count;
  fields_.push_back(std::move(desc));
  buffers_.emplace_back(data, data + count);
}

void PanelWriter::set_metadata(const std::string& json) {
  if (json.empty())
    throw std::invalid_argument("PanelWriter::set_metadata: empty metadata");
  metadata_ = json;
}

void PanelWriter::write(const std::string& path) {
  if (!panel_format::host_is_little_endian()) {
    throw std::runtime_error("PanelWriter::write: .qpanel requires a little-endian host");
  }
  const std::size_t count = n_sec_ * n_time_;
  if (fields_.size() > std::numeric_limits<std::uint32_t>::max()) {
    throw std::runtime_error("PanelWriter::write: too many fields for the v1 format");
  }
  const std::string sec_json = securities_to_json(secs_);

  // Section offsets; every section start and each field column is 64-byte aligned.
  const uint64_t sec_offset = kHeaderSize;
  const uint64_t sec_size = sec_json.size();
  const uint64_t meta_offset = align_up(sec_offset + sec_size, kAlignment);
  const uint64_t meta_size = metadata_.size();
  const uint64_t dates_offset = align_up(meta_offset + meta_size, kAlignment);
  const uint64_t dates_size = static_cast<uint64_t>(n_time_) * sizeof(int32_t);
  const uint64_t table_offset = align_up(dates_offset + dates_size, kAlignment);
  const uint64_t table_size = static_cast<uint64_t>(fields_.size()) * kFieldEntrySize;
  const uint64_t data_offset = align_up(table_offset + table_size, kAlignment);

  std::vector<uint64_t> column_offsets(fields_.size());
  uint64_t cursor = data_offset;
  for (std::size_t i = 0; i < fields_.size(); ++i) {
    column_offsets[i] = cursor;
    const uint64_t bytes = static_cast<uint64_t>(fields_[i].count) * sizeof(double);
    if (bytes > UINT64_MAX - kAlignment || cursor > UINT64_MAX - align_up(bytes, kAlignment)) {
      throw std::runtime_error("PanelWriter::write: panel too large for the v1 format");
    }
    cursor = align_up(cursor + bytes, kAlignment);
  }
  const uint64_t file_size = cursor;  // already 64-byte aligned

  Header header;
  header.version = panel_format::kVersion;
  header.header_size = kHeaderSize;
  header.flags = 0;
  header.field_count =
      static_cast<uint32_t>(fields_.size());  // field table size fits in u32 by format design
  header.file_size = file_size;
  header.n_sec = n_sec_;
  header.n_time = n_time_;
  header.content_hash = 0;  // patched after the payload is written
  header.sec_offset = sec_offset;
  header.sec_size = sec_size;
  header.meta_offset = meta_offset;
  header.meta_size = meta_size;
  header.dates_offset = dates_offset;
  header.dates_size = dates_size;
  header.table_offset = table_offset;
  header.table_size = table_size;
  header.data_offset = data_offset;

  static std::atomic<uint64_t> temp_counter{0};
  const std::filesystem::path target(path);
  std::filesystem::path temp = target;
  temp += ".tmp." + std::to_string(process_id()) + "." +
          std::to_string(temp_counter.fetch_add(1, std::memory_order_relaxed));

  bool temp_valid = false;
  try {
    std::ofstream out(temp, std::ios::binary | std::ios::trunc);
    if (!out) {
      throw std::runtime_error("PanelWriter::write: cannot create temporary file '" +
                               temp.string() + "'");
    }
    temp_valid = true;
    // Placeholder header; rewritten with the final content hash at the end.
    {
      const std::array<uint8_t, kHeaderSize> placeholder{};
      out.write(reinterpret_cast<const char*>(placeholder.data()),
                static_cast<std::streamsize>(placeholder.size()));
    }
    HashSink sink(out);
    sink.write_bytes(sec_json.data(), sec_json.size());
    sink.pad_to(meta_offset);
    sink.write_bytes(metadata_.data(), metadata_.size());
    sink.pad_to(dates_offset);

    std::vector<uint8_t> dates_bytes(static_cast<std::size_t>(dates_size));
    for (std::size_t t = 0; t < n_time_; ++t) {
      panel_format::put_u32(dates_bytes.data() + t * sizeof(uint32_t),
                            static_cast<uint32_t>(dates_[t]));
    }
    sink.write_bytes(dates_bytes.data(), dates_bytes.size());
    sink.pad_to(table_offset);

    std::vector<uint8_t> table(static_cast<std::size_t>(table_size));
    for (std::size_t i = 0; i < fields_.size(); ++i) {
      FieldEntry entry;
      std::memcpy(entry.name, fields_[i].name.data(), fields_[i].name.size());
      entry.layout = static_cast<uint32_t>(fields_[i].layout);
      entry.elem_size = fields_[i].elem_size;
      entry.offset = column_offsets[i];
      entry.count = fields_[i].count;
      const auto encoded = panel_format::encode_field_entry(entry);
      std::memcpy(table.data() + i * kFieldEntrySize, encoded.data(), encoded.size());
    }
    sink.write_bytes(table.data(), table.size());
    sink.pad_to(data_offset);

    for (std::size_t i = 0; i < fields_.size(); ++i) {
      if (buffers_[i].size() != count) {
        throw std::runtime_error("PanelWriter::write: field '" + fields_[i].name +
                                 "' has unexpected size");
      }
      sink.write_bytes(buffers_[i].data(), buffers_[i].size() * sizeof(double));
      const uint64_t next = (i + 1 < fields_.size()) ? column_offsets[i + 1] : file_size;
      sink.pad_to(next);
    }
    if (sink.offset() != file_size) {
      throw std::runtime_error("PanelWriter::write: internal layout mismatch");
    }
    header.content_hash = sink.hash();
    const auto encoded_header = panel_format::encode_header(header);
    out.seekp(0);
    out.write(reinterpret_cast<const char*>(encoded_header.data()),
              static_cast<std::streamsize>(encoded_header.size()));
    out.flush();
    if (!out)
      throw std::runtime_error("PanelWriter::write: failed to finalize '" + path + "'");
  } catch (...) {
    if (temp_valid) {
      std::error_code ignored;
      std::filesystem::remove(temp, ignored);
    }
    throw;
  }

  std::error_code ec;
#ifdef _WIN32
  // Never replace a file that may already be mapped by this or another process.
  if (std::filesystem::exists(target, ec) && !ec) {
    std::error_code ignored;
    std::filesystem::remove(temp, ignored);
    throw std::runtime_error(
        "PanelWriter::write: refusing to overwrite an existing .qpanel on Windows; "
        "write a new snapshot path instead (" +
        path + ")");
  }
  std::filesystem::rename(temp, target, ec);
#else
  std::filesystem::rename(temp, target, ec);  // atomic replace on POSIX
#endif
  if (ec) {
    std::error_code ignored;
    std::filesystem::remove(temp, ignored);
    throw std::runtime_error("PanelWriter::write: cannot move temporary file to '" + path +
                             "': " + ec.message());
  }
}

}  // namespace qc
