"""HTML → PDF report rendering via a locally installed Chrome/Chromium.

QuantCore ships HTML reports by default (zero extra dependencies). PDF export is optional
and uses the browser's own print-to-pdf path; if no Chrome/Chromium is available the
caller gets a clear error rather than a silently broken file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class PdfReportError(RuntimeError):
    """Raised when PDF rendering is unavailable or fails."""


_CANDIDATES = (
    os.environ.get("QC_CHROME"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "msedge",
)


def chrome_executable() -> str | None:
    """Return the first usable Chrome/Chromium executable, if any."""
    for candidate in _CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return None


def render_pdf(html_path: str | Path, pdf_path: str | Path, *, timeout: int = 90) -> Path:
    """Render an HTML file to PDF with headless Chrome; raise :class:`PdfReportError`."""
    source = Path(html_path).resolve()
    target = Path(pdf_path).resolve()
    if not source.is_file():
        raise PdfReportError(f"HTML report not found: {source}")
    executable = chrome_executable()
    if executable is None:
        raise PdfReportError(
            "Chrome/Chromium not found; set QC_CHROME or use the HTML report. "
            "PDF export is optional and requires a local browser."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--no-sandbox",
        f"--print-to-pdf={target}",
        source.as_uri(),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=timeout, text=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise PdfReportError(f"PDF rendering failed: {detail[:500]}") from exc
    if not target.is_file() or target.stat().st_size < 100:
        raise PdfReportError(f"PDF rendering produced no usable file: {target}")
    return target


def pdf_available() -> bool:
    return chrome_executable() is not None


__all__ = ["PdfReportError", "chrome_executable", "pdf_available", "render_pdf"]
