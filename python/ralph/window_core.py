"""Research-only draft of the frozen Kalshi 'one test'. Not the protected grader.

Inputs are private normalized JSONL files. Never print identifying rows or market tickers.
The authoritative scorer remains research/heatmap_live/score.ts; port/parity-test
against it before using these diagnostics for any gate or decision.
"""
from __future__ import annotations

import bisect
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Iterable

ENTRY_USD = 10.0
ENTRY_LAG_MS = 20_000
WINDOW_MS = 60_000
SAMPLE_GAP_MS = 25_000
HOLE_MS = 60_000
MIN_SIDE = 0.10
MAX_SIDE = 0.90
MARGIN_PER_CONTRACT = 0.01
MIN_PUBLIC_CELL = 5
POLICY = {
    "15m": {"entry_from_ms": 840_000, "entry_to_ms": 300_000,
            "deadline_before_close_ms": 90_000, "cluster_ms": 900_000},
    "hourly": {"entry_from_ms": 3_300_000, "entry_to_ms": 600_000,
               "deadline_before_close_ms": 360_000, "cluster_ms": 3_600_000},
}


def jsonl(path: str) -> Iterable[dict[str, Any]]:
    with open(path, encoding="utf8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("not an object")
                yield item
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"input line {n}: malformed JSONL") from exc


def date_utc(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def to_decimal(value: float | int) -> Decimal:
    return Decimal(str(value))


def taker_fee(n: int, side_price: float, *, rate: float = 0.07,
              multiplier: float = 1.0, balance_precision: float = 0.01) -> float:
    """Copy of the standard-tier whole-contract fee, with micro-dollar and balance rounding.

    Per-series fee-rate/precision overrides require separate verified evidence.
    The current TS function is bot/fees.ts. This is NOT an authoritative fee implementation.
    """
    if n < 1 or not 0 < side_price < 1:
        return 0.0
    p = to_decimal(side_price)
    trade = (to_decimal(multiplier) * to_decimal(rate) * n * p * (1 - p))
    micro = Decimal("0.000001")
    trade = trade.quantize(micro, rounding=ROUND_CEILING)
    amount = n * p + trade
    precision = to_decimal(balance_precision)
    charged = (amount / precision).to_integral_value(rounding=ROUND_CEILING) * precision
    return float(charged - n * p)


def side_ask(book: dict, side: str) -> float:
    return float(book["ya"]) if side == "yes" else 1 - float(book["yb"])


def side_bid(book: dict, side: str) -> float:
    return float(book["yb"]) if side == "yes" else 1 - float(book["ya"])


def side_bid_depth(book: dict, side: str) -> float:
    return float(book["ybs"]) if side == "yes" else float(book["yas"])


def two_sided(book: dict) -> bool:
    try:
        return 0 <= float(book["yb"]) < float(book["ya"]) <= 1
    except (KeyError, TypeError, ValueError):
        return False


def next_grid_price(at_least: float, market: dict) -> float | None:
    """First allowed bid >= threshold. Honors variable tick bands; does not invent a grid."""
    ranges = market.get("price_ranges")
    if not ranges:
        tick = float(market.get("tick", 0))
        if not 0 < tick <= 1:
            return None  # missing grid is not permission to assume 1 cent
        ranges = [{"start": 0, "end": 1, "step": tick}]
    choices = []
    for band in ranges:
        lo, hi, step = float(band["start"]), float(band["end"]), float(band["step"])
        if not 0 < step <= 1 or hi <= lo:
            continue
        k = max(0, math.ceil((at_least - lo - 1e-10) / step))
        x = round(lo + k * step, 4)
        if x >= at_least - 1e-9 and x <= hi + 1e-9 and x <= 1:
            choices.append(x)
    return min(choices) if choices else None


def exit_level(ask: float, contracts: int, market: dict) -> float | None:
    """Lowest price on the market's grid selling C clears both taker fees + 1c/C."""
    need = contracts * (ask + MARGIN_PER_CONTRACT) + taker_fee(contracts, ask)
    p = next_grid_price(ask, market)
    for _ in range(10_001):
        if p is None or p >= 1:
            return None
        if contracts * p - taker_fee(contracts, p) >= need - 1e-9:
            return p
        p = next_grid_price(round(p + 0.0001, 4), market)
    raise ValueError("invalid price grid: too many increments")


@dataclass(frozen=True)
class WindowScore:
    status: str
    hit: bool | None = None
    depth_hit: bool | None = None
    time_to_window_ms: int | None = None
    held_ms: int | None = None
    dip: float | None = None


def score_entry(market: dict, samples: list[dict], sample_times: list[int],
                side: str, at_ms: int, band: bool = True) -> WindowScore:
    """Matching research/heatmap_live/score.ts one-test semantics, excluding future outcome knowledge at entry."""
    i = bisect.bisect_left(sample_times, at_ms)
    if i >= len(samples) or sample_times[i] - at_ms > ENTRY_LAG_MS:
        return WindowScore("no-book")
    entry = samples[i]
    if not two_sided(entry):
        return WindowScore("one-sided")
    ask = round(side_ask(entry, side), 4)
    if band and not MIN_SIDE - 1e-9 <= ask <= MAX_SIDE + 1e-9:
        return WindowScore("out-of-band")
    n = max(1, int(math.floor(ENTRY_USD / ask + 1e-9)))
    level = exit_level(ask, n, market)
    deadline = int(market["close_ms"]) - POLICY[market["kind"]]["deadline_before_close_ms"]
    # Full-book rule: cannot treat missing quotes as a losing opportunity.
    prev = sample_times[i]
    end = i
    for j in range(i + 1, len(samples)):
        t = sample_times[j]
        if t > deadline:
            break
        if t - prev > HOLE_MS:
            return WindowScore("incomplete")
        prev, end = t, j
    if deadline - prev > HOLE_MS:
        return WindowScore("incomplete")
    last = -float("inf")
    run_start = None
    run_depth = None
    hit = depth_hit = False
    to_window = held = None
    dip = 0.0
    for j in range(i + 1, end + 1):
        s, t = samples[j], sample_times[j]
        if t - last > SAMPLE_GAP_MS:
            run_start = run_depth = None
        last = t
        bid = side_bid(s, side) if two_sided(s) else float("nan")
        if not hit and math.isfinite(bid):
            dip = min(dip, bid - ask)
        ok = level is not None and math.isfinite(bid) and bid >= level - 1e-9
        if not ok:
            run_start = run_depth = None
            continue
        if run_start is None:
            run_start = j
        if side_bid_depth(s, side) >= n:
            if run_depth is None:
                run_depth = j
        else:
            run_depth = None
        if t - sample_times[run_start] >= WINDOW_MS:
            hit = True
            if to_window is None:
                to_window = sample_times[run_start] - sample_times[i]
            held = t - sample_times[run_start]
        if run_depth is not None and t - sample_times[run_depth] >= WINDOW_MS:
            depth_hit = True
    return WindowScore("scored", hit, depth_hit, to_window, held, round(dip, 4))


def load_books(path: str) -> dict[str, tuple[list[dict], list[int]]]:
    indexed = defaultdict(list)
    for r in jsonl(path):
        # Runner must supply the required full day plus close-buffer of adjacent day.
        for k in ("ticker", "t_ms", "yb", "ya", "ybs", "yas"):
            if k not in r:
                raise ValueError(f"book input missing required {k}")
        indexed[str(r["ticker"])].append(r)
    result = {}
    for ticker, rows in indexed.items():
        rows.sort(key=lambda r: int(r["t_ms"]))
        times = [int(r["t_ms"]) for r in rows]
        if len(set(times)) != len(times):
            raise ValueError("duplicate book timestamp in one contract")
        result[ticker] = (rows, times)
    return result


def candidate_scores(calls_path: str, markets_path: str, books_path: str, day: str) -> tuple[list[dict], dict[str, int]]:
    """One contract entry per call selection; output must remain in private storage."""
    markets = {str(r["ticker"]): r for r in jsonl(markets_path)}
    books = load_books(books_path)
    calls = sorted(jsonl(calls_path), key=lambda r: (int(r["asof_ms"]), int(r.get("rank", 999999))))
    seen, out, excluded = set(), [], defaultdict(int)
    for call in calls:
        t = int(call["asof_ms"])
        if date_utc(t) != day:
            continue
        if call.get("kind") not in POLICY or call.get("h") != (15 if call.get("kind") == "15m" else 60):
            excluded["wrong-horizon"] += 1
            continue
        # Independently checked: the actual bot's one-call-per-coin + nearest-strike selection.
        if call.get("selector_verified") is not True:
            excluded["unverified-selection"] += 1
            continue
        if int(call.get("bar_close_ms", t + 1)) > t:
            excluded["future-call"] += 1
            continue
        ticker = str(call["ticker"])
        market = markets.get(ticker)
        if not market or market.get("kind") != call["kind"]:
            excluded["missing-market"] += 1
            continue
        if ticker in seen:
            excluded["duplicate-contract-candidate"] += 1
            continue
        until = int(market["close_ms"]) - t
        pol = POLICY[market["kind"]]
        if not (pol["entry_to_ms"] <= until <= pol["entry_from_ms"]):
            excluded["outside-entry-window"] += 1
            continue
        s, times = books.get(ticker, ([], []))
        side = call.get("side")
        if side not in ("yes", "no"):
            excluded["invalid-side"] += 1
            continue
        a = score_entry(market, s, times, side, t)
        if a.status in ("no-book", "one-sided", "out-of-band"):
            excluded[a.status] += 1
            continue
        seen.add(ticker)
        b = score_entry(market, s, times, "no" if side == "yes" else "yes", t, band=False)
        # Unequal coverage cannot create directional evidence.
        good = a.status == "scored" and b.status == "scored"
        if not good:
            excluded["incomplete-pair"] += 1
        out.append({
            "day": day, "asset": call["asset"], "kind": call["kind"],
            "side": side, "h": call["h"], "ticker": ticker, "asof_ms": t,
            "regime": call.get("regime", "unknown"),
            "pack_sha": call.get("pack_sha"), "call_key": call.get("call_key"),
            "source_mode": call.get("source_mode", "unspecified"),
            "status": "scored" if good else "incomplete",
            "called_window": a.hit if good else None,
            "opposite_window": b.hit if good else None,
            "called_depth_window": a.depth_hit if good else None,
            "to_window_ms": a.time_to_window_ms if good else None,
            "held_window_ms": a.held_ms if good else None,
            "dip": a.dip if good else None,
            "slot_ms": t // pol["cluster_ms"] * pol["cluster_ms"],
        })
    return out, dict(excluded)


def gap_of(r: dict) -> float:
    return (float(bool(r["called_window"])) - float(bool(r["opposite_window"]))) / 2.0


def bootstrapped_gap(rows: list[dict], seed: int = 20261111, iters: int = 2000) -> dict:
    """Resample 15-minute/hourly slot clusters, with all coins sharing their slot."""
    valid = [r for r in rows if r.get("status") == "scored"]
    groups = defaultdict(list)
    for r in valid:
        groups[(r["kind"], int(r["slot_ms"]))].append(gap_of(r))
    if len(groups) < 5:
        return {"n": len(valid), "clusters": len(groups), "gap": None, "se": None,
                "mde_gap": None, "above_2se": None}
    arr = list(groups.values())
    rng = random.Random(seed)
    point = sum(map(sum, arr)) / sum(map(len, arr))
    estimates = []
    for _ in range(iters):
        take = [arr[rng.randrange(len(arr))] for _ in arr]
        estimates.append(sum(map(sum, take)) / sum(map(len, take)))
    se = stdev(estimates)
    return {"n": len(valid), "clusters": len(arr), "gap": round(point, 6),
            "se": round(se, 6), "mde_gap": round(2 * se, 6),
            "above_2se": bool(point >= 2 * se and point > 0)}


def aggregate_public(rows: list[dict], exclusions: dict) -> dict:
    """Only aggregate counts, no tickers, curve keys, precise timestamps or small cells."""
    valid = [r for r in rows if r["status"] == "scored"]
    by_group = defaultdict(list)
    for r in valid:
        by_group[(r["asset"], r["side"], r["kind"])].append(r)
    splits = []
    for (asset, side, kind), xs in sorted(by_group.items()):
        if len(xs) < MIN_PUBLIC_CELL:
            continue
        splits.append({"coin": asset, "side": side, "kind": kind,
                       "n": len(xs), "window_rate": round(mean(int(bool(x["called_window"])) for x in xs), 5),
                       "random_side_rate": round(mean((int(bool(x["called_window"])) + int(bool(x["opposite_window"]))) / 2 for x in xs), 5),
                       "paired_gap": round(mean(gap_of(x) for x in xs), 5)})
    return {"schema": "ralph-direction-diagnostic-v1", "trial_count": 1,
            "called_rate": round(mean(int(bool(x["called_window"])) for x in valid), 6) if valid else None,
            "random_side_rate": round(mean((int(bool(x["called_window"])) + int(bool(x["opposite_window"]))) / 2 for x in valid), 6) if valid else None,
            "mean_time_to_window_ms": round(mean(x["to_window_ms"] for x in valid if x.get("to_window_ms") is not None), 2) if sum(x.get("to_window_ms") is not None for x in valid) >= MIN_PUBLIC_CELL else None,
            "mean_wrong_way_dip": round(mean(x["dip"] for x in valid if x.get("dip") is not None), 6) if len(valid) >= MIN_PUBLIC_CELL else None,
            "scored": len(valid), "unscored": len(rows) - len(valid),
            "excluded_by_reason": dict(exclusions), "score": bootstrapped_gap(rows), "splits": splits,
            "disclaimer": "Research diagnostics only; no binding grader pass, no promotion."}