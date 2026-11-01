#pragma once
// Internal .qpanel on-disk layout v1 (not part of the public qcore API).
//
//   offset 0            header, 256 bytes, little-endian scalars
//   sec_offset  (=256)  security directory as JSON: {"securities":[...]}
//   meta_offset         opaque metadata JSON text (Panel::metadata_json(), default "{}")
//   dates_offset        n_time int32 dates, YYYYMMDD
//   table_offset        field_count * 64B field directory entries
//   data_offset         field columns: count doubles each, columns 64B aligned
//   file_size           64B aligned; unused tail bytes are zero
//
// Every section offset is 64-byte aligned. content_hash is FNV-1a 64 (seed from the
// qc::fnv1a64 default) over bytes [kHeaderSize, file_size) exactly as stored.
// All multi-byte scalars are little-endian; doubles are IEEE-754 binary64 little-endian
// (host endianness is checked at runtime; every supported target is little-endian).
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "qcore/panel.h"

namespace qc::panel_format {

constexpr std::array<char, 8> kMagic = {'Q', 'P', 'A', 'N', 'E', 'L', '\0', '\0'};
constexpr uint32_t kVersion = 1;
constexpr uint32_t kHeaderSize = 256;
constexpr uint32_t kFieldEntrySize = 64;
constexpr uint64_t kAlignment = 64;
// Field names are stored NUL padded in 32 bytes, so at most 31 bytes are usable.
constexpr std::size_t kMaxFieldName = 31;

struct Header {
  uint32_t version = kVersion;
  uint32_t header_size = kHeaderSize;
  uint32_t flags = 0;
  uint32_t field_count = 0;
  uint64_t file_size = 0;
  uint64_t n_sec = 0;
  uint64_t n_time = 0;
  uint64_t content_hash = 0;
  uint64_t sec_offset = 0;
  uint64_t sec_size = 0;
  uint64_t meta_offset = 0;
  uint64_t meta_size = 0;
  uint64_t dates_offset = 0;
  uint64_t dates_size = 0;
  uint64_t table_offset = 0;
  uint64_t table_size = 0;
  uint64_t data_offset = 0;
};

struct FieldEntry {
  char name[32] = {};
  uint32_t layout = 0;
  uint32_t elem_size = 8;
  uint64_t offset = 0;
  uint64_t count = 0;
};

inline uint64_t align_up(uint64_t value, uint64_t alignment) {
  return (value + alignment - 1) / alignment * alignment;
}

inline bool host_is_little_endian() {
  const uint16_t probe = 1;
  unsigned char first = 0;
  std::memcpy(&first, &probe, sizeof(first));
  return first == 1;
}

inline void put_u32(uint8_t* p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
  p[2] = static_cast<uint8_t>(v >> 16);
  p[3] = static_cast<uint8_t>(v >> 24);
}

inline void put_u64(uint8_t* p, uint64_t v) {
  for (int i = 0; i < 8; ++i)
    p[i] = static_cast<uint8_t>(v >> (8 * i));
}

inline uint32_t get_u32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

inline uint64_t get_u64(const uint8_t* p) {
  uint64_t v = 0;
  for (int i = 0; i < 8; ++i)
    v |= static_cast<uint64_t>(p[i]) << (8 * i);
  return v;
}

// 256-byte header serialization. Layout (all little-endian):
//   [0,8) magic | [8,12) version | [12,16) header_size | [16,20) flags |
//   [20,24) field_count | [24,32) file_size | [32,40) n_sec | [40,48) n_time |
//   [48,56) content_hash | [56,64) sec_offset | [64,72) sec_size |
//   [72,80) meta_offset | [80,88) meta_size | [88,96) dates_offset |
//   [96,104) dates_size | [104,112) table_offset | [112,120) table_size |
//   [120,128) data_offset | [128,256) reserved zero.
inline std::array<uint8_t, kHeaderSize> encode_header(const Header& h) {
  std::array<uint8_t, kHeaderSize> out{};
  for (std::size_t i = 0; i < kMagic.size(); ++i)
    out[i] = static_cast<uint8_t>(kMagic[i]);
  put_u32(out.data() + 8, h.version);
  put_u32(out.data() + 12, h.header_size);
  put_u32(out.data() + 16, h.flags);
  put_u32(out.data() + 20, h.field_count);
  put_u64(out.data() + 24, h.file_size);
  put_u64(out.data() + 32, h.n_sec);
  put_u64(out.data() + 40, h.n_time);
  put_u64(out.data() + 48, h.content_hash);
  put_u64(out.data() + 56, h.sec_offset);
  put_u64(out.data() + 64, h.sec_size);
  put_u64(out.data() + 72, h.meta_offset);
  put_u64(out.data() + 80, h.meta_size);
  put_u64(out.data() + 88, h.dates_offset);
  put_u64(out.data() + 96, h.dates_size);
  put_u64(out.data() + 104, h.table_offset);
  put_u64(out.data() + 112, h.table_size);
  put_u64(out.data() + 120, h.data_offset);
  return out;
}

inline Header decode_header(const uint8_t* p) {
  Header h;
  h.version = get_u32(p + 8);
  h.header_size = get_u32(p + 12);
  h.flags = get_u32(p + 16);
  h.field_count = get_u32(p + 20);
  h.file_size = get_u64(p + 24);
  h.n_sec = get_u64(p + 32);
  h.n_time = get_u64(p + 40);
  h.content_hash = get_u64(p + 48);
  h.sec_offset = get_u64(p + 56);
  h.sec_size = get_u64(p + 64);
  h.meta_offset = get_u64(p + 72);
  h.meta_size = get_u64(p + 80);
  h.dates_offset = get_u64(p + 88);
  h.dates_size = get_u64(p + 96);
  h.table_offset = get_u64(p + 104);
  h.table_size = get_u64(p + 112);
  h.data_offset = get_u64(p + 120);
  return h;
}

// 64-byte field directory entry: name[32] | layout u32 | elem_size u32 | offset u64 |
// count u64 | reserved 8 bytes zero.
inline std::array<uint8_t, kFieldEntrySize> encode_field_entry(const FieldEntry& f) {
  std::array<uint8_t, kFieldEntrySize> out{};
  std::memcpy(out.data(), f.name, sizeof(f.name));
  put_u32(out.data() + 32, f.layout);
  put_u32(out.data() + 36, f.elem_size);
  put_u64(out.data() + 40, f.offset);
  put_u64(out.data() + 48, f.count);
  return out;
}

inline FieldEntry decode_field_entry(const uint8_t* p) {
  FieldEntry f;
  std::memcpy(f.name, p, sizeof(f.name));
  f.layout = get_u32(p + 32);
  f.elem_size = get_u32(p + 36);
  f.offset = get_u64(p + 40);
  f.count = get_u64(p + 48);
  return f;
}

}  // namespace qc::panel_format
