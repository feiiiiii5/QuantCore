"""Shared support for public-web history providers (Sina / Eastmoney fallbacks).

Contains code/board helpers, tolerant JSON parsing for Sina JSON-v2 / Tencent payloads,
payload parsers (Sina universe snapshot, Sina daily bars, Tencent forward-adjusted closes),
canonical bar assembly and approximate adjustment / corporate-action derivation.

Consumers must already have normalised units: volume in shares, amount in CNY, prices in
CNY. Derived corporate actions are approximations (rounding-noise bound based) and are
labelled with the caller's source string, e.g. SINA_APPROX.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..calendar import to_date_int
from ..data.panel import BARS_REQUIRED, normalize_bars
from ..data.synthetic_rules import BOARD_LIMIT, ST_LIMIT, ST_LIMIT_AFTER, ST_LIMIT_CHANGE_DATE
from ..errors import ProviderError

ACTION_COLUMNS: tuple[str, ...] = (
    "sec_id",
    "ann_date",
    "record_date",
    "ex_date",
    "pay_date",
    "cash_per_share",
    "split_ratio",
    "rights_ratio",
    "rights_price",
    "source",
)
_BARE_KEY_RE = re.compile(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


# -- code / board helpers ----------------------------------------------------
def normalize_code(value: str | int) -> str:
    """Normalise 600000 / sh600000 / SH.600000 / 600000.SH to a 6-digit code."""
    text = str(value).strip().upper().replace("-", ".")
    if "." in text:
        left, right = text.split(".", 1)
        exchange_tokens = {"SH", "SZ", "BJ", "BSE", "SS"}
        text = right if left in exchange_tokens else left
    elif text[:2] in {"SH", "SZ", "BJ"}:
        text = text[2:]
    if not (text.isdigit() and len(text) == 6):
        raise ProviderError(f"invalid A-share code: {value!r}")
    return text


def infer_board(code: str) -> str:
    """Board from the code prefix (60x/00x MAIN, 30x GEM, 68x STAR, 4/8/92x BSE)."""
    text = normalize_code(code)
    if text.startswith(("60", "00")):
        return "MAIN"
    if text.startswith("30"):
        return "GEM"
    if text.startswith("68"):
        return "STAR"
    if text.startswith(("4", "8", "92")):
        return "BSE"
    raise ProviderError(f"cannot infer the board for code {code!r}")


def infer_exchange(code: str) -> str:
    """Exchange code SH / SZ / BJ for an A-share code."""
    text = normalize_code(code)
    if text.startswith("6"):
        return "SH"
    if text.startswith(("4", "8", "92")):
        return "BJ"
    return "SZ"


def code_to_sec_id(value: str) -> tuple[str, str]:
    """Map a code-like value to (sec_id, exchange), e.g. ('SH.600000', 'SH')."""
    code = normalize_code(value)
    exchange = infer_exchange(code)
    return f"{exchange}.{code}", exchange


def sina_symbol(value: str) -> str:
    """Sina/Tencent symbol prefix (sh/sz/bj) plus the 6-digit code."""
    code = normalize_code(value)
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[infer_exchange(code)]
    return f"{prefix}{code}"


def parse_public_json(text: str) -> Any:
    """Parse a Sina/Tencent public response; supports strict JSON and bare-key JSON-v2.

    A literal null or an empty body means no data and returns None.
    """
    candidate = text.strip().lstrip("\ufeff")
    if not candidate or candidate == "null":
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        quoted = _BARE_KEY_RE.sub(r'\1"\2":', candidate)
        try:
            return json.loads(quoted)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"cannot parse public JSON response ({exc}); sample={candidate[:160]!r}"
            ) from exc


# -- Sina payload parsing ----------------------------------------------------
def normalize_sina_universe(payload: Any) -> pd.DataFrame:
    """Normalise the hs_a snapshot rows to the canonical security master."""
    rows: list[dict[str, Any]] = []
    records = payload if isinstance(payload, list) else []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        try:
            code = normalize_code(str(item.get("code") or item.get("symbol") or ""))
            board = infer_board(code)
        except ProviderError:
            continue
        sec_id, exchange = code_to_sec_id(code)
        rows.append(
            {
                "sec_id": sec_id,
                "code": code,
                "exchange": exchange,
                "name": str(item.get("name") or "").strip(),
                "board": board,
                "list_date": 0,  # TODO(verify): the hs_a snapshot carries no list date
                "delist_date": 0,
                "sec_type": "STOCK",
                "industry": "",
                "source": "SINA",
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=[
            "sec_id",
            "code",
            "exchange",
            "name",
            "board",
            "list_date",
            "delist_date",
            "sec_type",
            "industry",
            "source",
        ],
    )
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    return frame


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def parse_sina_daily(payload: Any, code: str) -> pd.DataFrame:
    """Parse getKLineData rows: volume is already shares; no amount is provided."""
    records = payload if isinstance(payload, list) else []
    rows: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        raw_day = item.get("day")
        if raw_day is None:
            continue
        try:
            day = to_date_int(str(raw_day))
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "date": day,
                "open": _number(item.get("open")),
                "high": _number(item.get("high")),
                "low": _number(item.get("low")),
                "close": _number(item.get("close")),
                "volume": _number(item.get("volume")),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["date", "sec_id", "open", "high", "low", "close", "volume"])
    code_norm = normalize_code(code)
    frame["sec_id"] = code_to_sec_id(code_norm)[0]
    frame["code"] = code_norm
    frame["volume"] = frame["volume"].fillna(0).round().astype("int64")  # shares as-is
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    return frame.sort_values("date", kind="stable").reset_index(drop=True)


def parse_tencent_qfq(payload: Any, symbol: str) -> pd.DataFrame:
    """Parse Tencent fqkline qfq rows to a date/close frame (adjusted, CNY)."""
    data = payload.get("data") if isinstance(payload, Mapping) else None
    entry = data.get(symbol) if isinstance(data, Mapping) else None
    rows = None
    if isinstance(entry, Mapping):
        rows = entry.get("qfqday") or entry.get("day")
    records = rows if isinstance(rows, list) else []
    parsed: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        try:
            day = to_date_int(item[0])
            close = float(item[2])
        except (TypeError, ValueError):
            continue
        parsed.append({"date": day, "close": close})
    frame = pd.DataFrame(parsed, columns=["date", "close"])
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def empty_public_bars() -> pd.DataFrame:
    """Empty canonical bars frame with stable dtypes."""
    return normalize_bars(
        pd.DataFrame({column: pd.Series(dtype=object) for column in BARS_REQUIRED})
    )


def empty_corporate_actions() -> pd.DataFrame:
    return pd.DataFrame(columns=list(ACTION_COLUMNS))


def build_canonical_bars(
    raw: pd.DataFrame, factor: pd.Series, *, board: str, st: bool, source: str
) -> pd.DataFrame:
    """Assemble canonical raw-price bars; pre_close follows the derived adjustment.

    If the raw frame has no amount column, amount is estimated from
    volume x mean(open, high, low, close); magnitude only (not a real traded value).
    """
    if raw.empty:
        return empty_public_bars()
    bars = raw.copy().reset_index(drop=True)
    bars["adj_factor"] = factor.reset_index(drop=True).astype("float64")
    close = bars["close"].to_numpy(dtype=float)
    factors = bars["adj_factor"].to_numpy(dtype=float)
    pre_close = np.empty(len(bars), dtype=float)
    pre_close[0] = close[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(factors[1:] > 0, factors[:-1] / factors[1:], 1.0)
    pre_close[1:] = np.round(close[:-1] * ratio, 2)
    bars["pre_close"] = pre_close
    if "amount" not in bars.columns or bars["amount"].isna().all():
        average = bars[["open", "high", "low", "close"]].mean(axis=1)
        bars["amount"] = (bars["volume"].astype(float) * average).round(2)
    dates = bars["date"].to_numpy(dtype=int)
    pct = np.full(len(bars), BOARD_LIMIT[board], dtype=float)
    if st and board == "MAIN":
        pct = np.where(dates < ST_LIMIT_CHANGE_DATE, ST_LIMIT, ST_LIMIT_AFTER)
    bars["limit_up"] = np.round(pre_close * (1.0 + pct), 2)
    bars["limit_down"] = np.round(pre_close * (1.0 - pct), 2)
    bars["suspended"] = False
    bars["st"] = bool(st)
    for column in ("total_shares", "float_shares"):
        bars[column] = 0
    for column in ("mktcap", "float_mktcap"):
        bars[column] = 0.0
    if "turnover" in bars.columns:
        bars["turnover"] = pd.to_numeric(bars["turnover"], errors="coerce").fillna(0.0)
    else:
        bars["turnover"] = 0.0
    bars["source"] = source
    return normalize_bars(bars)


def derive_adjustment(
    raw: pd.DataFrame, adjusted: pd.DataFrame, *, source: str = "PUBLIC_WEB_APPROX"
) -> tuple[pd.Series, pd.DataFrame]:
    """Derive adj_factor (forward-adjusted / raw close) and approximate actions.

    A factor jump above the rounding-noise bound max(0.2%, 0.02/price) marks an ex-date;
    small jumps are treated as cash dividends, large ones as splits. EXPECTED columns:
    raw needs date/close/sec_id, adjusted needs date/close.
    """
    factors = pd.Series(1.0, index=raw.index, dtype="float64")
    if raw.empty or adjusted.empty or "sec_id" not in raw.columns:
        return factors, empty_corporate_actions()
    raw_rows = raw[["date", "close"]].drop_duplicates(subset=["date"], keep="last")
    adjusted_rows = adjusted[["date", "close"]].drop_duplicates(subset=["date"], keep="last")
    merged = raw_rows.merge(adjusted_rows, on="date", how="inner", suffixes=("_raw", "_adj"))
    merged = merged[(merged["close_raw"] > 0) & (merged["close_adj"] > 0)].reset_index(drop=True)
    if merged.empty:
        return factors, empty_corporate_actions()
    raw_ratio = (merged["close_adj"] / merged["close_raw"]).round(6).to_numpy(dtype=float)
    close_raw = merged["close_raw"].to_numpy(dtype=float)
    # adj_factor is non-decreasing, so a higher qfq/raw ratio is a candidate new level.
    # Vendor qfq series occasionally contain one-off glitches (for example a ratio bump on
    # a limit-up day); accepting them would fabricate ex-dates and break pre_close/limit
    # consistency.  Only commit a jump when it (a) exceeds rounding noise, (b) persists for
    # the following observations and (c) keeps the forward-adjusted daily return inside the
    # exchange limit.
    confirm_days = min(5, max(1, len(raw_ratio) - 1))
    eps = 0.002
    accepted = np.empty(len(raw_ratio), dtype=float)
    # Start from the median of the first observations: one noisy leading bar must not shift
    # the baseline factor for the whole series.
    current = float(np.median(raw_ratio[: min(5, len(raw_ratio))]))
    accepted[0] = current
    candidate_start: int | None = None
    blocked_level: float | None = None
    for index in range(1, len(raw_ratio)):
        value = float(raw_ratio[index])
        baseline = float(close_raw[index - 1]) if close_raw[index - 1] > 0 else 0.0
        min_jump = max(0.005, 0.02 / baseline) if baseline > 0 else 0.005
        level_above = value > current * (1.0 + min_jump)
        if not level_above:
            candidate_start = None
            blocked_level = None
        elif candidate_start is None:
            candidate_start = index
            # Judge the jump on its first day: a genuine ex-dividend leaves the adjusted
            # (qfq) daily return inside the price limit, while a vendor ratio glitch on a
            # limit-up day pushes it past ~11%.  Block implausible levels for good instead
            # of accepting them later when the raw price drifts.
            previous_close = float(close_raw[index - 1])
            jump_implied = 0.0
            if previous_close > 0:
                jump_implied = float((value * close_raw[index]) / (current * previous_close)) - 1.0
            if abs(jump_implied) > 0.11 or value / current > 2.5:
                blocked_level = value
        if level_above and candidate_start is not None and blocked_level is None:
            window = raw_ratio[index + 1 : index + 1 + confirm_days]
            sustained = bool(window.size) and bool(np.all(window >= value * (1.0 - eps)))
            if sustained:
                current = value
                candidate_start = None
        accepted[index] = current
    merged["factor"] = accepted
    factor_map = dict(zip(merged["date"].tolist(), accepted.tolist(), strict=False))
    factors = raw["date"].map(factor_map).ffill().bfill().fillna(1.0).astype("float64")
    breaks: list[tuple[int, float, float]] = []
    previous_factor: float | None = None
    previous_close = 0.0
    for day, factor_value, raw_close in zip(
        merged["date"].tolist(),
        merged["factor"].tolist(),
        merged["close_raw"].tolist(),
        strict=False,
    ):
        close_value = float(raw_close)
        if previous_factor is not None and previous_factor > 0 and previous_close > 0:
            jump = float(factor_value) / previous_factor
            if jump > 1.0 + max(0.002, 0.02 / previous_close):
                breaks.append((int(day), jump, previous_close))
        previous_factor, previous_close = float(factor_value), close_value
    sec_id = str(raw["sec_id"].iloc[0])
    actions: list[dict[str, Any]] = [
        {
            "sec_id": sec_id,
            "ann_date": 0,
            "record_date": 0,
            "ex_date": ex_date,
            "pay_date": 0,
            "cash_per_share": 0.0 if jump >= 1.2 else round(previous * (jump - 1.0) / jump, 4),
            "split_ratio": float(np.round(jump, 2)) if jump >= 1.2 else 1.0,
            "rights_ratio": 0.0,
            "rights_price": 0.0,
            "source": source,
        }
        for ex_date, jump, previous in breaks
    ]
    return factors, pd.DataFrame(actions, columns=list(ACTION_COLUMNS))
