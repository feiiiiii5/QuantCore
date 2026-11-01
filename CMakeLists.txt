cmake_minimum_required(VERSION 3.26)
project(QuantCore VERSION 0.1.0 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
enable_testing()

option(QC_BUILD_PYTHON "Build pybind11 extension" ON)
option(QC_BUILD_TESTS "Build C++ tests" ON)
option(QC_BUILD_BENCH "Build C++ benchmarks" ON)
option(QC_BUILD_FUZZ "Build fuzz targets" OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# Warnings; no -ffast-math, no FMA contraction.
if(MSVC)
  add_compile_options(/W4 /WX /permissive- /Zc:__cplusplus)
else()
  add_compile_options(-Wall -Wextra -Wpedantic -Werror -Wno-unused-parameter
                      -fno-fast-math -ffp-contract=off)
endif()

file(GLOB_RECURSE QC_CORE_SOURCES CONFIGURE_DEPENDS
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/core/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/panel/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/kernels/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/expr/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/sim/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/analytics/*.cpp
     ${CMAKE_CURRENT_SOURCE_DIR}/cpp/src/sweep/*.cpp)
if(NOT QC_CORE_SOURCES)
  message(FATAL_ERROR "No qcore sources found under cpp/src")
endif()

add_library(qcore STATIC ${QC_CORE_SOURCES})
target_include_directories(qcore PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)
target_compile_features(qcore PUBLIC cxx_std_20)

if(QC_BUILD_PYTHON)
  find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
  find_package(pybind11 CONFIG REQUIRED)
  file(GLOB_RECURSE QC_BINDING_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/cpp/bindings/*.cpp)
  pybind11_add_module(_qcore ${QC_BINDING_SOURCES})
  target_link_libraries(_qcore PRIVATE qcore)
  target_include_directories(_qcore PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)
  install(TARGETS _qcore LIBRARY DESTINATION quantcore)
endif()

if(QC_BUILD_TESTS)
  include(FetchContent)
  FetchContent_Declare(Catch2 URL https://codeload.github.com/catchorg/Catch2/tar.gz/refs/tags/v3.8.0)
  FetchContent_MakeAvailable(Catch2)
  list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
  file(GLOB_RECURSE QC_TEST_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/cpp/tests/*.cpp)
  add_executable(qcore_tests ${QC_TEST_SOURCES})
  target_link_libraries(qcore_tests PRIVATE qcore Catch2::Catch2WithMain)
  include(Catch)
  catch_discover_tests(qcore_tests)
endif()

if(QC_BUILD_BENCH)
  include(FetchContent)
  FetchContent_Declare(google_benchmark URL https://codeload.github.com/google/benchmark/tar.gz/refs/tags/v1.9.1)
  set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(google_benchmark)
  file(GLOB_RECURSE QC_BENCH_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/cpp/bench/*.cpp)
  add_executable(qcore_bench ${QC_BENCH_SOURCES})
  target_link_libraries(qcore_bench PRIVATE qcore benchmark::benchmark benchmark::benchmark_main)
endif()
