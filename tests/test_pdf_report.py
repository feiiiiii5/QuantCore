"""M4-009 optional PDF report export via local Chrome/Chromium."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantcore.report_pdf import PdfReportError, pdf_available, render_pdf


def test_pdf_smoke(tmp_path: Path) -> None:
    if not pdf_available():
        pytest.skip("Chrome/Chromium not installed; PDF export is optional")
    html = tmp_path / "report.html"
    html.write_text(
        "<html><body><h1>QuantCore PDF</h1><p>smoke</p></body></html>", encoding="utf-8"
    )
    target = render_pdf(html, tmp_path / "report.pdf")
    assert target.read_bytes().startswith(b"%PDF")
    assert target.stat().st_size > 100


def test_pdf_missing_html_raises(tmp_path: Path) -> None:
    with pytest.raises(PdfReportError, match="HTML report not found"):
        render_pdf(tmp_path / "missing.html", tmp_path / "out.pdf")


def test_pdf_api_endpoint(api_client, seeded_experiment) -> None:
    if not pdf_available():
        pytest.skip("Chrome/Chromium not installed; PDF export is optional")
    run_id = seeded_experiment.run_id
    response = api_client.get(f"/api/experiments/{run_id}/report.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")
