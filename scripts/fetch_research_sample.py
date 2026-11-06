"""Download a non-PIT Sina sample explicitly, or finalize its local checkpoints offline."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import signal
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
from research_signal_adjustment import causal_factors

from quantcore.calendar import TradingCalendar, date_str
from quantcore.data.panel import PanelData
from quantcore.data.store import ParquetStore
from quantcore.providers.public_web import (
    build_canonical_bars,
    derive_adjustment,
    infer_board,
    normalize_sina_universe,
    parse_public_json,
    parse_sina_daily,
    parse_tencent_qfq,
)
from quantcore.providers.sina import REQUEST_HEADERS, SINA_KLINE_URL, TENCENT_QFQ_URL, SinaProvider
from quantcore.quality import run_quality_checks
from quantcore.realtime.quotes import SINA_URL, parse_sina_payload, sina_symbol

CODES = ["000001", "000063", "000100", "000333", "000568", "000651", "000725", "000858"]


def finalize_cached(output: Path, start: str, end: str) -> PanelData:
    """Rebuild only the jointly covered, validated span without network access."""
    fetched: list[str] = []

    def cached(kind: str, params: dict) -> str:
        key = hashlib.sha256(json.dumps([kind, params], sort_keys=True).encode()).hexdigest()
        saved = json.loads((output / ".fetch-cache" / f"{key}.json").read_text())
        fetched.append(saved["fetched_at"])
        return saved["text"]

    quotes = parse_sina_payload(cached("quote", {}))
    names = {quote.code: quote.name for quote in quotes}
    if set(names) != set(CODES) or any("ST" in name.upper() for name in names.values()):
        raise ValueError("missing quote-derived master or ST security")
    raw, adjusted = {}, {}
    for code in CODES:
        params = {"symbol": sina_symbol(code), "scale": 240, "ma": "no", "datalen": 2000}
        raw[code] = parse_sina_daily(parse_public_json(cached("kline", params)), code)
        first = date_str(int(raw[code].date.min()))
        query = {"param": f"{sina_symbol(code)},day,{first},{end},2000,qfq"}
        adjusted[code] = parse_tencent_qfq(
            parse_public_json(cached("qfq", query)), sina_symbol(code)
        )
    available = list(raw.values()) + list(adjusted.values())
    lo = max(int(start.replace("-", "")), *(int(frame.date.min()) for frame in available))
    hi = min(int(end.replace("-", "")), *(int(frame.date.max()) for frame in available))
    if lo > hi:
        raise ValueError("adjusted series have no common coverage")
    frames, events = [], []
    for code in CODES:
        window = raw[code][raw[code].date.between(lo, hi)].reset_index(drop=True)
        qfq = adjusted[code][adjusted[code].date.between(lo, hi)].copy()
        _, actions = derive_adjustment(window, qfq, source="SINA_APPROX")
        factors = causal_factors(window, actions)
        frames.append(
            build_canonical_bars(
                window, factors, board=infer_board(code), st=False, source="SINA", actions=actions
            )
        )
        events.append(actions)
    index_params = {"symbol": "sh000001", "scale": 240, "ma": "no", "datalen": 2000}
    index = parse_sina_daily(parse_public_json(cached("index_kline", index_params)), "000001")
    meta = {
        "provider": "sina",
        "source": "SINA",
        "synthetic": False,
        "codes": CODES,
        "curated_sample": True,
        "non_pit_master": True,
        "master_origin": "quote-derived current master; list/delist_date=0 means unknown",
        "universe_note": "8 surviving SZ MAIN stocks; selection/survivorship bias; historical ST status unknown",
        "amount_note": "estimated volume times mean OHLC; not observed turnover value",
        "actions_note": "cash-only additive qfq model verified on aligned OHLC; SINA_APPROX cash events remain approximate",
        "signal_adjustment": "causal_ex_date_events",
        "event_provenance": "SINA_APPROX inferred cash events; no official point-in-time proof",
        "raw_requested_start": start,
        "raw_requested_end": end,
        "raw_cache_preserved": True,
        "validated_span": {"start": lo, "end": hi},
        "raw_coverage": {
            code: {
                "start": int(raw[code].date.min()),
                "end": int(raw[code].date.max()),
                "rows": len(raw[code]),
            }
            for code in CODES
        },
        "adjusted_coverage": {
            code: {
                "start": int(adjusted[code].date.min()),
                "end": int(adjusted[code].date.max()),
                "rows": len(adjusted[code]),
            }
            for code in CODES
        },
        "fetched_at": max(fetched),
        "fetch_started_at": min(fetched),
        "finalized_offline": True,
    }
    return PanelData(
        calendar=TradingCalendar.from_dates(index.date.tolist()).slice(lo, hi),
        securities=normalize_sina_universe([{"code": code, "name": names[code]} for code in CODES]),
        bars=pd.concat(frames, ignore_index=True),
        corporate_actions=pd.concat(events, ignore_index=True),
        meta=meta,
    )


def persist(panel: PanelData, output: Path, report_name: str) -> None:
    report = run_quality_checks(panel)
    report.write(output / report_name)
    report.raise_if_failed()
    store = ParquetStore(output / "warehouse")
    store.write_panel(panel)
    store.set_metadata("quality", report.to_dict())
    print(
        json.dumps(
            {
                "rows": len(panel.bars),
                "start": int(panel.bars.date.min()),
                "end": int(panel.bars.date.max()),
                "by_code": panel.bars.groupby("code")
                .date.agg(["min", "max", "count"])
                .to_dict("index"),
                "actions": len(panel.corporate_actions),
                "quality": report.to_dict(),
                "data_hash": store.manifest_hash(),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--finalize-offline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/research-q005"))
    parser.add_argument("--start", default="2019-01-02")
    parser.add_argument("--end", default="2026-11-06")
    args = parser.parse_args()
    if not args.allow_network and not args.finalize_offline:
        parser.error("choose --allow-network to download or --finalize-offline to use checkpoints")
    if args.allow_network and args.finalize_offline:
        parser.error("offline finalization cannot be combined with --allow-network")
    manifest = args.output / "warehouse" / "warehouse_manifest.json"
    if manifest.exists():
        existing = json.loads(manifest.read_text()).get("metadata", {}).get("panel_meta", {})
        if not (
            args.finalize_offline
            and existing.get("finalized_offline") is True
            and existing.get("codes") == CODES
            and existing.get("provider") == "sina"
            and existing.get("source") == "SINA"
            and existing.get("synthetic") is False
            and existing.get("curated_sample") is True
            and existing.get("non_pit_master") is True
            and existing.get("signal_adjustment") == "causal_ex_date_events"
            and existing.get("raw_requested_start") == args.start
            and existing.get("raw_requested_end") == args.end
        ):
            parser.error("output contains a different warehouse; choose a new output directory")
    if args.finalize_offline:
        persist(
            finalize_cached(args.output, args.start, args.end),
            args.output,
            "quality_report_validated_span.json",
        )
        return
    cache = args.output / ".fetch-cache"
    cache.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 48
    signal.signal(
        signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("55s download budget"))
    )
    signal.alarm(55)

    def get_text(kind: str, params: dict) -> str:
        key = hashlib.sha256(json.dumps([kind, params], sort_keys=True).encode()).hexdigest()
        checkpoint = cache / f"{key}.json"
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text())
            return saved["text"]
        limiter.acquire()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("network budget exhausted; rerun to reuse checkpoints")
        url = {"quote": SINA_URL, "qfq": TENCENT_QFQ_URL}.get(kind, SINA_KLINE_URL)
        if kind in {"index_kline", "kline"}:
            url = url.replace("money.finance.sina.com.cn", "vip.stock.finance.sina.com.cn")
        if kind == "quote":
            url += ",".join(sina_symbol(code) for code in CODES)

        async def request() -> bytes:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=REQUEST_HEADERS)
                response.raise_for_status()
                return response.content

        try:
            raw = asyncio.run(asyncio.wait_for(request(), timeout=min(6, remaining)))
        except Exception as exc:
            raise RuntimeError(
                f"{kind} {params}: {type(exc).__name__} within 6s; checkpoints retained"
            ) from exc
        text = raw.decode("gb18030") if kind == "quote" else raw.decode("utf-8-sig")
        stamp = datetime.now(UTC).isoformat()
        checkpoint.write_text(json.dumps({"fetched_at": stamp, "text": text}, ensure_ascii=False))
        return text

    limiter = SinaProvider(allow_network=True).limiter
    try:
        # Download the same exact cache keys consumed by finalize_cached. Keeping
        # acquisition separate also permits intersecting raw/adjusted coverage
        # before deriving events, rather than persisting vendor qfq price ratios.
        get_text("quote", {})
        for code in CODES:
            params = {"symbol": sina_symbol(code), "scale": 240, "ma": "no", "datalen": 2000}
            raw = parse_sina_daily(parse_public_json(get_text("kline", params)), code)
            if raw.empty:
                raise ValueError(f"missing raw history for {code}")
            first = date_str(int(raw.date.min()))
            get_text("qfq", {"param": f"{sina_symbol(code)},day,{first},{args.end},2000,qfq"})
        get_text("index_kline", {"symbol": "sh000001", "scale": 240, "ma": "no", "datalen": 2000})
    finally:
        signal.alarm(0)
    persist(
        finalize_cached(args.output, args.start, args.end),
        args.output,
        "quality_report_validated_span.json",
    )


if __name__ == "__main__":
    main()
