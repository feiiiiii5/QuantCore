// Panel::open: memory-maps a .qpanel v1 file read-only (shared) after validating magic,
// version, section bounds/alignment, sizes, dates, the security directory and the field
// table. Fast open is O(n_time + n_sec + fields); open(path, true) / validate(path) also
// verify the whole-payload FNV-1a content hash. Any inconsistency throws std::runtime_error.
#include "qcore/panel.h"

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <filesystem>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#include "panel_format.h"

namespace qc {
namespace {

using panel_format::align_up;
using panel_format::decode_field_entry;
using panel_format::decode_header;
using panel_format::FieldEntry;
using panel_format::Header;
using panel_format::kAlignment;
using panel_format::kFieldEntrySize;
using panel_format::kHeaderSize;
using panel_format::kMagic;
using panel_format::kVersion;

void* map_readonly(const std::string& path, std::size_t& out_size) {
  out_size = 0;
#ifdef _WIN32
  const std::wstring wide = std::filesystem::path(path).wstring();
  HANDLE file = ::CreateFileW(wide.c_str(), GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) {
    throw std::runtime_error("Panel::open: cannot open '" + path + "' (win32 error " +
                             std::to_string(::GetLastError()) + ")");
  }
  LARGE_INTEGER size{};
  if (::GetFileSizeEx(file, &size) == 0) {
    const DWORD error = ::GetLastError();
    ::CloseHandle(file);
    throw std::runtime_error("Panel::open: cannot stat '" + path + "' (win32 error " +
                             std::to_string(error) + ")");
  }
  if (size.QuadPart <= 0 ||
      static_cast<unsigned long long>(size.QuadPart) >
          static_cast<unsigned long long>(std::numeric_limits<std::size_t>::max())) {
    ::CloseHandle(file);
    throw std::runtime_error("Panel::open: empty or oversized file '" + path + "'");
  }
  HANDLE mapping = ::CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
  ::CloseHandle(file);
  if (mapping == nullptr) {
    throw std::runtime_error("Panel::open: cannot map '" + path + "' (win32 error " +
                             std::to_string(::GetLastError()) + ")");
  }
  void* view = ::MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0);
  ::CloseHandle(mapping);
  if (view == nullptr) {
    throw std::runtime_error("Panel::open: cannot map view of '" + path + "' (win32 error " +
                             std::to_string(::GetLastError()) + ")");
  }
  out_size = static_cast<std::size_t>(size.QuadPart);
  return view;
#else
  const int fd = ::open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    throw std::runtime_error("Panel::open: cannot open '" + path + "': " + std::strerror(errno));
  }
  struct stat st {};
  if (::fstat(fd, &st) != 0) {
    const int error = errno;
    ::close(fd);
    throw std::runtime_error("Panel::open: cannot stat '" + path + "': " +
                             std::strerror(error));
  }
  if (st.st_size <= 0 ||
      static_cast<unsigned long long>(st.st_size) >
          static_cast<unsigned long long>(std::numeric_limits<std::size_t>::max())) {
    ::close(fd);
    throw std::runtime_error("Panel::open: empty or oversized file '" + path + "'");
  }
  const auto size = static_cast<std::size_t>(st.st_size);
  void* view = ::mmap(nullptr, size, PROT_READ, MAP_SHARED, fd, 0);
  const int error = errno;
  ::close(fd);
  if (view == MAP_FAILED) {
    throw std::runtime_error("Panel::open: mmap failed for '" + path + "': " +
                             std::strerror(error));
  }
  out_size = size;
  return view;
#endif
}

void unmap_readonly(void* view, std::size_t size) {
  if (view == nullptr) return;
#ifdef _WIN32
  (void)size;
  ::UnmapViewOfFile(view);
#else
  if (size != 0) ::munmap(view, size);
#endif
}

void require_section(const std::size_t file_size, const char* what, uint64_t offset,
                     uint64_t length) {
  if (offset > file_size || length > file_size - offset) {
    throw std::runtime_error(std::string("Panel::open: ") + what + " section out of bounds");
  }
  if ((offset % kAlignment) != 0) {
    throw std::runtime_error(std::string("Panel::open: ") + what + " section is not 64B aligned");
  }
}

}  // namespace

Panel Panel::open(const std::string& path, bool verify_content) {
  if (!panel_format::host_is_little_endian()) {
    throw std::runtime_error("Panel::open: .qpanel requires a little-endian host");
  }
  std::size_t file_size = 0;
  void* view = map_readonly(path, file_size);
  try {
    if (file_size < kHeaderSize) {
      throw std::runtime_error("Panel::open: '" + path + "' is smaller than the header");
    }
    const auto* base = static_cast<const uint8_t*>(view);
    if (std::memcmp(base, kMagic.data(), kMagic.size()) != 0) {
      throw std::runtime_error("Panel::open: bad magic in '" + path + "' (not a .qpanel file)");
    }
    const Header header = decode_header(base);
    if (header.version != kVersion) {
      throw std::runtime_error("Panel::open: unsupported .qpanel version " +
                               std::to_string(header.version) + " in '" + path + "'");
    }
    if (header.header_size != kHeaderSize) {
      throw std::runtime_error("Panel::open: unexpected header size in '" + path + "'");
    }
    if (header.flags != 0) {
      throw std::runtime_error("Panel::open: unknown header flags in '" + path + "'");
    }
    if (header.file_size != file_size) {
      throw std::runtime_error("Panel::open: file size mismatch in '" + path + "' (header " +
                               std::to_string(header.file_size) + ", actual " +
                               std::to_string(file_size) + ")");
    }
    if (header.n_sec == 0 || header.n_time == 0) {
      throw std::runtime_error("Panel::open: empty panel in '" + path + "'");
    }
    if (header.n_sec > std::numeric_limits<std::size_t>::max() / header.n_time) {
      throw std::runtime_error("Panel::open: panel dimensions overflow in '" + path + "'");
    }
    const std::size_t n_sec = static_cast<std::size_t>(header.n_sec);
    const std::size_t n_time = static_cast<std::size_t>(header.n_time);
    const std::size_t cell_count = n_sec * n_time;

    require_section(file_size, "security directory", header.sec_offset, header.sec_size);
    require_section(file_size, "metadata", header.meta_offset, header.meta_size);
    require_section(file_size, "dates", header.dates_offset, header.dates_size);
    require_section(file_size, "field table", header.table_offset, header.table_size);
    require_section(file_size, "data", header.data_offset, 0);
    if (header.sec_offset != kHeaderSize) {
      throw std::runtime_error("Panel::open: security directory must follow the header");
    }
    if (header.dates_size != static_cast<uint64_t>(n_time) * sizeof(int32_t)) {
      throw std::runtime_error("Panel::open: dates section has an unexpected size");
    }
    if (header.table_size != static_cast<uint64_t>(header.field_count) * kFieldEntrySize) {
      throw std::runtime_error("Panel::open: field table has an unexpected size");
    }
    // Sections are contiguous with 64B padding in canonical v1 files; require the canonical
    // layout so that offsets can never point into another section.
    if (header.meta_offset != align_up(header.sec_offset + header.sec_size, kAlignment) ||
        header.dates_offset != align_up(header.meta_offset + header.meta_size, kAlignment) ||
        header.table_offset != align_up(header.dates_offset + header.dates_size, kAlignment) ||
        header.data_offset != align_up(header.table_offset + header.table_size, kAlignment)) {
      throw std::runtime_error("Panel::open: non-canonical section layout in '" + path + "'");
    }
    if (verify_content) {
      const uint64_t payload_size = file_size - kHeaderSize;
      const uint64_t actual_hash =
          fnv1a64(base + kHeaderSize, static_cast<std::size_t>(payload_size));
      if (actual_hash != header.content_hash) {
        throw std::runtime_error("Panel::open: content hash mismatch in '" + path +
                                 "' (file corrupted or truncated)");
      }
    }

    Panel panel;
    panel.file_size_ = file_size;
    panel.n_sec_ = n_sec;
    panel.n_time_ = n_time;
    panel.content_hash_ = header.content_hash;
    panel.metadata_ =
        std::string(reinterpret_cast<const char*>(base + header.meta_offset), header.meta_size);
    panel.dates_.reserve(n_time);
    for (std::size_t t = 0; t < n_time; ++t) {
      const Date date =
          static_cast<Date>(panel_format::get_u32(base + header.dates_offset + t * sizeof(uint32_t)));
      if (!valid_date(date)) {
        throw std::runtime_error("Panel::open: invalid date " + std::to_string(date) +
                                 " at time row " + std::to_string(t));
      }
      if (t > 0 && date <= panel.dates_[t - 1]) {
        throw std::runtime_error("Panel::open: dates are not strictly increasing (row " +
                                 std::to_string(t) + ")");
      }
      panel.dates_.push_back(date);
    }
    try {
      panel.securities_ = securities_from_json(
          std::string(reinterpret_cast<const char*>(base + header.sec_offset), header.sec_size));
    } catch (const std::exception& e) {
      throw std::runtime_error("Panel::open: invalid security directory in '" + path +
                               "': " + e.what());
    }
    if (panel.securities_.size() != n_sec) {
      throw std::runtime_error("Panel::open: security directory has " +
                               std::to_string(panel.securities_.size()) + " rows, expected " +
                               std::to_string(n_sec));
    }
    std::unordered_set<std::string> names;
    names.reserve(static_cast<std::size_t>(header.field_count) * 2 + 8);
    for (std::size_t i = 0; i < header.field_count; ++i) {
      const auto* entry_bytes = base + header.table_offset + i * kFieldEntrySize;
      const FieldEntry entry = decode_field_entry(entry_bytes);
      const void* nul = std::memchr(entry.name, '\0', sizeof(entry.name));
      if (nul == nullptr) {
        throw std::runtime_error("Panel::open: field name is not NUL terminated at index " +
                                 std::to_string(i));
      }
      const std::size_t name_len =
          static_cast<std::size_t>(static_cast<const char*>(nul) - entry.name);
      if (name_len == 0) {
        throw std::runtime_error("Panel::open: empty field name at index " + std::to_string(i));
      }
      const std::string name(entry.name, name_len);
      if (entry.layout > 1) {
        throw std::runtime_error("Panel::open: field '" + name + "' has an unknown layout");
      }
      if (entry.elem_size != sizeof(double)) {
        throw std::runtime_error("Panel::open: field '" + name + "' has an unexpected elem_size");
      }
      if (entry.offset < header.data_offset || entry.offset > file_size ||
          (entry.offset % kAlignment) != 0) {
        throw std::runtime_error("Panel::open: field '" + name + "' has an invalid column offset");
      }
      if (entry.count != cell_count) {
        throw std::runtime_error("Panel::open: field '" + name +
                                 "' has an unexpected element count");
      }
      if (entry.count > (file_size - entry.offset) / sizeof(double)) {
        throw std::runtime_error("Panel::open: field '" + name + "' column out of bounds");
      }
      if (!names.insert(name).second) {
        throw std::runtime_error("Panel::open: duplicate field '" + name + "'");
      }
      FieldDesc desc;
      desc.name = name;
      desc.layout = static_cast<Layout>(entry.layout);
      desc.elem_size = entry.elem_size;
      desc.offset = entry.offset;
      desc.count = entry.count;
      panel.fields_.emplace(name, std::move(desc));
    }
    panel.map_ = view;
    return panel;
  } catch (...) {
    unmap_readonly(view, file_size);
    throw;
  }
}

void Panel::validate(const std::string& path) {
  Panel panel = open(path, /*verify_content=*/true);
  (void)panel;
}

Panel::~Panel() {
  if (map_ != nullptr) {
    unmap_readonly(map_, file_size_);
    map_ = nullptr;
    file_size_ = 0;
  }
}

Panel::Panel(Panel&& other) noexcept
    : map_(other.map_),
      file_size_(other.file_size_),
      n_sec_(other.n_sec_),
      n_time_(other.n_time_),
      content_hash_(other.content_hash_),
      metadata_(std::move(other.metadata_)),
      dates_(std::move(other.dates_)),
      securities_(std::move(other.securities_)),
      fields_(std::move(other.fields_)) {
  other.map_ = nullptr;
  other.file_size_ = 0;
  other.n_sec_ = 0;
  other.n_time_ = 0;
  other.content_hash_ = 0;
}

Panel& Panel::operator=(Panel&& other) noexcept {
  if (this == &other) return *this;
  if (map_ != nullptr) {
    unmap_readonly(map_, file_size_);
  }
  map_ = other.map_;
  file_size_ = other.file_size_;
  n_sec_ = other.n_sec_;
  n_time_ = other.n_time_;
  content_hash_ = other.content_hash_;
  metadata_ = std::move(other.metadata_);
  dates_ = std::move(other.dates_);
  securities_ = std::move(other.securities_);
  fields_ = std::move(other.fields_);
  other.map_ = nullptr;
  other.file_size_ = 0;
  other.n_sec_ = 0;
  other.n_time_ = 0;
  other.content_hash_ = 0;
  return *this;
}

std::vector<std::string> Panel::field_names() const {
  std::vector<std::string> names;
  names.reserve(fields_.size());
  for (const auto& entry : fields_) names.push_back(entry.first);
  std::sort(names.begin(), names.end());
  return names;
}

FieldView Panel::field(const std::string& name) const {
  const auto it = fields_.find(name);
  if (it == fields_.end()) {
    throw std::runtime_error("Panel::field: unknown field '" + name + "'");
  }
  const FieldDesc& desc = it->second;
  FieldView view;
  view.data = reinterpret_cast<const double*>(static_cast<const uint8_t*>(map_) + desc.offset);
  view.layout = desc.layout;
  view.n_sec = n_sec_;
  view.n_time = n_time_;
  return view;
}

}  // namespace qc
