# DEV-SETUP — 开发环境（中国大陆网络）

## 工具链
- macOS Apple Silicon（开发机）或 Windows；CMake ≥3.26、Ninja、Apple clang ≥15 / MSVC 2022。
- Python 3.12（uv 管理）；Node ≥20、pnpm。
- 可选：clang-format、clang-tidy；GitHub Actions 覆盖 macOS arm64 / Windows / Ubuntu。

## 镜像（写入 shell 配置或 Makefile 环境）
```bash
# uv / pip
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
# npm
npm config set registry https://registry.npmmirror.com
pnpm config set registry https://registry.npmmirror.com
# Homebrew（可选）
export HOMEBREW_API_DOMAIN=https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles/api
export HOMEBREW_BOTTLE_DOMAIN=https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles
```

## 依赖获取
- C++：Catch2 / Google Benchmark 通过 CMake FetchContent 从 GitHub codeload 拉取；pybind11 通过 scikit-build-core 的 build-requires（PyPI）。
- Python：`uv sync`；前端：`pnpm install`；运行期零 CDN/字体外链。

## 外网受限时
- 先换镜像/重试；仍失败则记录 `PROGRESS.md`，用 Synthetic + fixture 继续开发，不阻塞其他任务。
