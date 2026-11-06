#include <catch2/catch_test_macros.hpp>
#include "qcore/version.h"
TEST_CASE("version and backend", "[smoke]") {
  REQUIRE(qc::version() == "0.1.1");
  REQUIRE(std::string(qc::engine_backend()) == "cpp");
}
