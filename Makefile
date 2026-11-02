SHELL := /bin/bash
UV ?= uv
CMAKE ?= cmake
NINJA ?= ninja
BUILD_DIR ?= build/cmake
PYTHON_VERSION ?= 3.12
export UV_DEFAULT_INDEX ?= https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL ?= https://pypi.tuna.tsinghua.edu.cn/simple
export UV_HTTP_TIMEOUT ?= 120

.PHONY: setup setup-ui build test test-quick doctor demo bench bench-scale lint verify-cpp verify-local perf-gate ui-check e2e desktop-smoke ci-local package sbom audit release fmt clean cmake configure

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

test-quick:
	$(UV) run pytest -q -m "not e2e and not bench and not network"

doctor:
	$(UV) run qc doctor --no-json-output

demo:
	$(UV) run qc demo

bench: build
	$(UV) run python scripts/bench.py
	./$(BUILD_DIR)/qcore_bench --benchmark_min_time=0.2s

bench-scale:
	$(UV) run python scripts/scale_bench.py

lint:
	$(UV) run ruff check python tests
	$(UV) run ruff format --check python tests
	$(UV) run mypy python/quantcore
	@command -v clang-format >/dev/null && find cpp -name '*.h' -o -name '*.cpp' | xargs clang-format --dry-run --Werror || echo "clang-format missing: skipped"

verify-cpp: build
	$(UV) run python scripts/verify_cpp.py

perf-gate: build
	$(UV) run python scripts/perf_gate.py

e2e:
	@$(UV) run pytest -q -m e2e; code=$$?; if [ $$code -ne 0 ] && [ $$code -ne 5 ]; then exit $$code; fi
	pnpm -C ui test
	bash scripts/e2e.sh

verify-local:
	bash scripts/local_verify.sh

ui-check:
	pnpm -C ui test
	pnpm -C ui build

desktop-smoke:
	bash scripts/desktop_smoke.sh

ci-local: setup lint test verify-cpp ui-check
	@echo "ci-local passed"

package:
	$(UV) build
	@if [ -d ui ] && [ -f ui/package.json ]; then pnpm -C ui build; fi

sbom:
	$(UV) run python scripts/sbom.py

audit:
	$(UV) run python scripts/audit.py

release:
	bash scripts/release.sh

fmt:
	@command -v clang-format >/dev/null && find cpp -name '*.h' -o -name '*.cpp' | xargs clang-format -i || true
	$(UV) run ruff format python tests

clean:
	rm -rf $(BUILD_DIR) build dist .pytest_cache .mypy_cache .ruff_cache
