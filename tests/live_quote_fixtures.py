"""Small recorded transport shared by live API and quote-freshness tests."""

import datetime as dt
import json
from pathlib import Path

from quantcore.realtime.clock import SHANGHAI_TZ

FIXTURES = Path(__file__).parent / "fixtures" / "live"


def _eastmoney_payload() -> dict:
    return json.loads((FIXTURES / "eastmoney_ulist.json").read_text(encoding="utf-8"))


def _sina_text() -> str:
    return (FIXTURES / "sina_quotes.txt").read_text(encoding="utf-8")


def _at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=SHANGHAI_TZ)


class FakeHttp:
    """Request-aware fake transport backed by the recorded fixtures."""

    def __init__(self, *, fail_json: bool = False) -> None:
        self.fail_json = fail_json
        self.json_calls = 0
        self.text_calls = 0
        self.index_rows = [_eastmoney_payload()["data"]["diff"][2]]
        self.stock_rows = _eastmoney_payload()["data"]["diff"][:2]
        for row in self.index_rows + self.stock_rows:
            row["f124"] = int(_at("2026-11-02T10:15:30").timestamp())

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None):
        self.json_calls += 1
        if self.fail_json:
            raise ConnectionError("eastmoney blocked (simulated)")
        rows = (
            list(self.index_rows)
            if ("1.000001" in url or "0.399001" in url)
            else list(self.stock_rows)
        )
        return {"data": {"total": len(rows), "diff": rows}}

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        self.text_calls += 1
        lines = _sina_text().splitlines()
        if "sh000001" in url or "sz399001" in url:
            return lines[2]
        return "\n".join(lines[:2])
