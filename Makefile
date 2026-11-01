SHELL := /bin/bash
UV ?= uv
CMAKE ?= cmake
NINJA ?= ninja
BUILD_DIR ?= build/cmake
PYTHON_VERSION ?= 3.12
export UV_DEFAULT_INDEX ?= https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL ?= https://pypi.tuna.tsinghua.edu.cn/simple
export UV_HTTP_TIMEOUT ?= 120

.PHONY: setup build test bench lint verify-cpp e2e ci-local package fmt clean cmake configure

setup:
	$(UV) python install $(PYTHON_VERSION)
	$(UV) sync --all-extras --python $(PYTHON_VERSION)
	$(MAKE) build

setup-ui:
	pnpm -C ui install

build:
	$(UV) sync --reinstall-package quantcore --all-extras --python $(PYTHON_VERSION)
	$(CMAKE) -S . -B $(BUILD_DIR) -G Ninja -DCMAKE_BUILD_TYPE=Release -DQC_BUILD_PYTHON=OFF -DQC_BUILD_TESTS=ON -DQC_BUILD_BENCH=ON
	$(CMAKE) --build $(BUILD_DIR)

cmake:
	$(CMAKE) -S . -B $(BUILD_DIR) -G Ninja -DCMAKE_BUILD_TYPE=Release -DQC_BUILD_PYTHON=OFF

test: build
	$(UV) run pytest -q
	ctest --test-dir $(BUILD_DIR) --output-on-failure

bench: build
	$(UV) run python scripts/bench.py
	./$(BUILD_DIR)/qcore_bench --benchmark_min_time=0.2s

lint:
	$(UV) run ruff check python tests
	$(UV) run ruff format --check python tests
	$(UV) run mypy python/quantcore
	@command -v clang-format >/dev/null && find cpp -name '*.h' -o -name '*.cpp' | xargs clang-format --dry-run --Werror || echo "clang-format missing: skipped"

verify-cpp: build
	$(UV) run python scripts/verify_cpp.py

e2e:
	@echo "e2e requires M5/M6 (FastAPI + UI); see docs/PROGRESS.md"
	$(UV) run pytest -q -m e2e
	pnpm -C ui test

ci-local: setup lint test verify-cpp
	@echo "ci-local passed"

package:
	$(UV) build
	@if [ -d ui ] && [ -f ui/package.json ]; then pnpm -C ui build; fi

fmt:
	@command -v clang-format >/dev/null && find cpp -name '*.h' -o -name '*.cpp' | xargs clang-format -i || true
	$(UV) run ruff format python tests

clean:
	rm -rf $(BUILD_DIR) build dist .pytest_cache .mypy_cache .ruff_cache
