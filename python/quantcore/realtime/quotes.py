"""Read-only A-share quote clients: Eastmoney primary, Sina fallback.

Both endpoints are public, token-free HTTP JSON/CSV-ish services.  Nothing here places
orders or touches a broker.  Live access is opt-in (QC_ALLOW_NETWORK=1) and the default
test suite only exercises the pure parsers against recorded fixtures.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ..errors import QuantCoreError
from .clock import now_shanghai

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 QuantCore/0.1"
)
EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
SINA_URL = "https://hq.sinajs.cn/list="
EASTMONEY_REFERER = "https://quote.eastmoney.com/"
SINA_REFERER = "https://finance.sina.com.cn"

#: Index quotes shown in the app bar and the Today page.
INDEX_SPECS: tuple[dict[str, str], ...] = (
    {"code": "000001", "name": "上证指数", "secid": "1.000001", "sina": "sh000001"},
    {"code": "399001", "name": "深证成指", "secid": "0.399001", "sina": "sz399001"},
    {"code": "399006", "name": "创业板指", "secid": "0.399006", "sina": "sz399006"},
    {"code": "000688", "name": "科创50", "secid": "1.000688", "sina": "sh000688"},
)

_INDEX_BY_CODE = {item["code"]: item for item in INDEX_SPECS}
_CODE_RE = re.compile(r"^[0-9]{6}$")


class QuoteSourceError(QuantCoreError):
    """Raised when every configured quote source fails."""


@dataclass(frozen=True)
class Quote:
    """One normalized real-time quote (read-only)."""

    code: str
    name: str
    price: float
    prev_close: float
    open: float | None
    high: float | None
    low: float | None
    change: float
    change_pct: float
    volume: float
    amount: float
    turnover_pct: float | None
    limit_up: float | None
    limit_down: float | None
    suspended: bool
    timestamp: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "prev_close": self.prev_close,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "amount": self.amount,
            "turnover_pct": self.turnover_pct,
            "limit_up": self.limit_up,
            "limit_down": self.limit_down,
            "suspended": self.suspended,
            "timestamp": self.timestamp,
            "source": self.source,
        }


class QuoteHttp(Protocol):
    """Minimal async HTTP surface; tests inject a fixture-backed fake."""

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any: ...

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str: ...


class HttpxQuoteHttp:
    """Default HTTP client used by the local server (never in tests)."""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            raw = response.content
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError:  # pragma: no cover - defensive
            return raw.decode("utf-8", errors="replace")


def normalize_code(code: str) -> str:
    text = str(code).strip()
    if not _CODE_RE.match(text):
        raise ValueError(f"invalid A-share code: {code!r} (expected 6 digits)")
    return text


def is_index_code(code: str) -> bool:
    return code in _INDEX_BY_CODE


def _market_id(code: str) -> int:
    """Eastmoney market id: 1 = Shanghai, 0 = Shenzhen/Beijing."""
    return 1 if code[0] in {"6", "9"} else 0


INDEX_PREFIX = "idx:"


def normalize_target(target: str) -> str:
    """Normalise a stock code or an idx:NNNNNN index target."""
    text = str(target).strip().lower()
    if text.startswith(INDEX_PREFIX):
        code = normalize_code(text[len(INDEX_PREFIX) :])
        if code not in _INDEX_BY_CODE:
            raise ValueError(f"unknown index: {target!r}")
        return f"{INDEX_PREFIX}{code}"
    return normalize_code(text)


def secid(target: str) -> str:
    if target.startswith(INDEX_PREFIX):
        return _INDEX_BY_CODE[target[len(INDEX_PREFIX) :]]["secid"]
    return f"{_market_id(normalize_code(target))}.{target}"


def sina_symbol(target: str) -> str:
    if target.startswith(INDEX_PREFIX):
        return _INDEX_BY_CODE[target[len(INDEX_PREFIX) :]]["sina"]
    code = normalize_code(target)
    if code[0] in {"6", "9"}:
        return f"sh{code}"
    if code[0] in {"4", "8"}:
        return f"bj{code}"
    return f"sz{code}"


def _num(value: Any) -> float | None:
    if value is None or value == "" or value in {"-", "--"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN check


def _quote_from_numbers(
    *,
    code: str,
    name: str,
    price: float | None,
    prev_close: float | None,
    open_: float | None,
    high: float | None,
    low: float | None,
    volume: float,
    amount: float,
    turnover: float | None,
    limit_up: float | None,
    limit_down: float | None,
    timestamp: str | None,
    source: str,
    now: dt.datetime,
) -> Quote | None:
    prev = prev_close or 0.0
    if price is None or price <= 0:
        # Closed/suspended sessions: fall back to the previous close as the display price.
        if prev <= 0:
            return None
        price = prev
        suspended = True
    else:
        suspended = False
    # Pre-open / halted rows report 0 for OHLC: keep them nullable instead of showing 0.00.
    open_value = open_ if (open_ is not None and open_ > 0) else None
    high_value = high if (high is not None and high > 0) else None
    low_value = low if (low is not None and low > 0) else None
    change = price - prev if prev > 0 else 0.0
    change_pct = (change / prev * 100.0) if prev > 0 else 0.0
    return Quote(
        code=code,
        name=name,
        price=round(price, 4),
        prev_close=round(prev, 4),
        open=None if open_value is None else round(open_value, 4),
        high=None if high_value is None else round(high_value, 4),
        low=None if low_value is None else round(low_value, 4),
        change=round(change, 4),
        change_pct=round(change_pct, 4),
        volume=round(float(volume), 2),
        amount=round(float(amount), 2),
        turnover_pct=None if turnover is None else round(turnover, 4),
        limit_up=None if limit_up is None else round(limit_up, 4),
        limit_down=None if limit_down is None else round(limit_down, 4),
        suspended=bool(suspended),
        timestamp=timestamp,
        source=source,
    )


def parse_eastmoney_payload(
    payload: Any, *, now: dt.datetime | None = None, as_index: bool = False
) -> list[Quote]:
    """Parse an Eastmoney ulist.np payload into normalized quotes."""
    now = now or now_shanghai()
    data = (payload or {}).get("data") or {}
    rows = data.get("diff") or []
    quotes: list[Quote] = []
    for row in rows:
        raw_code = str(row.get("f12") or "")
        if not _CODE_RE.match(raw_code):
            continue
        code = f"{INDEX_PREFIX}{raw_code}" if as_index else raw_code
        # Eastmoney volume field f5 is in lots (手) for stocks: convert to shares.
        volume_lots = _num(row.get("f5")) or 0.0
        quote = _quote_from_numbers(
            code=code,
            name=str(row.get("f14") or code),
            price=_num(row.get("f2")),
            prev_close=_num(row.get("f18")),
            open_=_num(row.get("f17")),
            high=_num(row.get("f15")),
            low=_num(row.get("f16")),
            volume=volume_lots * 100.0,
            amount=_num(row.get("f6")) or 0.0,
            turnover=_num(row.get("f8")),
            limit_up=_num(row.get("f51")),
            limit_down=_num(row.get("f52")),
            timestamp=now.isoformat(timespec="seconds"),
            source="eastmoney",
            now=now,
        )
        if quote is not None:
            quotes.append(quote)
    return quotes


_SINA_LINE = re.compile(r'var hq_str_([a-z]{2}[0-9]{6})="(.*)";')


def parse_sina_payload(
    text: str, *, now: dt.datetime | None = None, as_index: bool = False
) -> list[Quote]:
    """Parse Sina hq.sinajs.cn text into normalized quotes."""
    now = now or now_shanghai()
    quotes: list[Quote] = []
    for line in (text or "").splitlines():
        match = _SINA_LINE.search(line.strip())
        if not match:
            continue
        symbol, body = match.group(1), match.group(2)
        fields = body.split(",")
        if len(fields) < 10 or not fields[0]:
            continue
        raw_code = symbol[-6:]
        code = f"{INDEX_PREFIX}{raw_code}" if as_index else raw_code
        name = fields[0]
        open_, prev, price, high, low = (
            _num(fields[1]),
            _num(fields[2]),
            _num(fields[3]),
            _num(fields[4]),
            _num(fields[5]),
        )
        volume = _num(fields[8]) or 0.0  # shares for stocks and index aggregates
        amount = _num(fields[9]) or 0.0
        stamp = None
        if len(fields) >= 32 and fields[30] and fields[31]:
            stamp = f"{fields[30]}T{fields[31]}"
        quote = _quote_from_numbers(
            code=code,
            name=name,
            price=price,
            prev_close=prev,
            open_=open_,
            high=high,
            low=low,
            volume=volume,
            amount=amount,
            turnover=None,
            limit_up=None,
            limit_down=None,
            timestamp=stamp or now.isoformat(timespec="seconds"),
            source="sina",
            now=now,
        )
        if quote is not None:
            quotes.append(quote)
    return quotes


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def fetch_eastmoney_quotes(
    http: QuoteHttp,
    codes: list[str],
    *,
    now: dt.datetime | None = None,
    as_index: bool = False,
) -> list[Quote]:
    """Fetch quotes from Eastmoney in batches (max 50 symbols per call)."""
    now = now or now_shanghai()
    quotes: list[Quote] = []
    for batch in _chunks([normalize_target(code) for code in codes], 50):
        secids = ",".join(secid(code) for code in batch)
        fields = "f12,f13,f14,f2,f3,f4,f5,f6,f8,f15,f16,f17,f18,f51,f52"
        url = f"{EASTMONEY_URL}?fltt=2&invt=2&fields={fields}&secids={secids}"
        payload = await http.get_json(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": EASTMONEY_REFERER},
        )
        quotes.extend(parse_eastmoney_payload(payload, now=now, as_index=as_index))
    return quotes


async def fetch_sina_quotes(
    http: QuoteHttp,
    codes: list[str],
    *,
    now: dt.datetime | None = None,
    as_index: bool = False,
) -> list[Quote]:
    """Fetch quotes from Sina in batches (max 60 symbols per call)."""
    now = now or now_shanghai()
    quotes: list[Quote] = []
    for batch in _chunks([normalize_target(code) for code in codes], 60):
        url = SINA_URL + ",".join(sina_symbol(code) for code in batch)
        text = await http.get_text(url, headers={"User-Agent": USER_AGENT, "Referer": SINA_REFERER})
        quotes.extend(parse_sina_payload(text, now=now, as_index=as_index))
    return quotes


__all__ = [
    "EASTMONEY_URL",
    "INDEX_PREFIX",
    "INDEX_SPECS",
    "SINA_URL",
    "Quote",
    "QuoteHttp",
    "QuoteSourceError",
    "fetch_eastmoney_quotes",
    "fetch_sina_quotes",
    "is_index_code",
    "normalize_code",
    "normalize_target",
    "parse_eastmoney_payload",
    "parse_sina_payload",
    "secid",
    "sina_symbol",
]
