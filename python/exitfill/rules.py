"""Frozen fill rules (see README.md). Everything is in held-side terms and integer 1e-4 price units.

For each paper exit at decision time t0 the question is: had a SELL been resting from t0 + slack instead of the
reduce-only IOC at bid minus two ticks, would it have filled within H seconds, at what price, and what would the
fallback IOC at t0 + slack + H have cost? Two book-implied fill rules (neither is a bound that can be proven):
  strict: a held-side bid at or above q + 1 tick is displayed after placement. A resting bid cannot coexist with an
          ask at or below it, so every ask at q was removed; with price-time priority and no impact we were hit.
  touch : the held-side best bid is at least q. A buyer rests at q, so we were hit at least in part.
An ask level that disappears without the bid reaching q is counted as ambiguous (a cancel and a trade look the same)
and never credited. Unsold contracts (no bid at the fallback, or beyond the 3 stored levels) are valued at zero
proceeds in every arm, and counted.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import FLOOR_TICKS, GAP_MS, NEAR_CLOSE_MS, PLACEMENT_SLACK_MS, UNIT, VARIANTS
from .book import Capture, HeldBook, HeldGrid, Grid, Sample, TickerSeries, close_ms, held_book, kind_of
from .events import Exit

from allpairs.fees import maker_fee, taker_fee  # read-only import of the exact bot fee port (python/ on sys.path)


def rules_hash() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    for name in ('__init__.py', 'rules.py'):
        with open(os.path.join(here, name), 'rb') as fh:
            h.update(fh.read())
    return h.hexdigest()[:12]


@dataclass(frozen=True)
class Walk:
    sold: float
    proceeds: float
    fee: float
    short: float


def ioc_floor(bid_u: int, hg: HeldGrid) -> int:
    f = bid_u
    for _ in range(FLOOR_TICKS):
        f -= hg.down(f)
    return f


def walk_ioc(bids, count: float, floor_u: int) -> Walk:
    """Sell `count` into the stored bid levels down to `floor_u`; the taker fee is charged per level fill, as the paper
    exchange does. Whatever the levels cannot absorb is short and earns nothing."""
    rem, proceeds, fee = float(count), 0.0, 0.0
    for p, z in bids:
        if p < floor_u or rem <= 1e-9:
            break
        take = min(rem, z)
        proceeds += take * p / UNIT
        fee += float(taker_fee(take, p / UNIT))
        rem -= take
    return Walk(count - max(rem, 0.0), proceeds, fee, max(rem, 0.0))


@dataclass(frozen=True)
class Order:
    variant: str
    q: int
    queue: float


def place(variant: str, hb: HeldBook, hg: HeldGrid, ref_bid_u: Optional[int]) -> Optional[Order]:
    if not hb.bids or not hb.asks:
        return None
    b0, a0 = hb.bids[0][0], hb.asks[0][0]
    if a0 <= b0:
        return None
    if variant == 'JOIN_ASK':
        q, queue = a0, hb.asks[0][1]
    elif variant == 'INSIDE':
        q, queue = a0 - hg.down(a0), 0.0
        if q <= b0:
            return None
    elif variant == 'BID_PLUS_1C':
        q, queue = b0 + 100, 0.0
        if q >= a0:
            return None
    else:
        raise ValueError(variant)
    if ref_bid_u is not None and q <= ref_bid_u:
        return None   # at the bid the bot actually saw this would have been a taker, not a resting order
    return Order(variant, q, queue)


@dataclass(frozen=True)
class Hit:
    k: int
    prev_t: int
    qty: float
    first: bool   # seen in the very first evidence sample: the cross may have predated the order


@dataclass(frozen=True)
class Passage:
    strict: Optional[Hit]
    touch: Optional[Hit]
    cleared_k: Optional[int]


@dataclass
class Ctx:
    ex: Exit
    shift: int
    t0: int
    tp: int
    ts: TickerSeries
    i0: int
    s0: Sample
    hb0: HeldBook
    hg: HeldGrid
    close: Optional[int]
    kind: str


def make_ctx(ex: Exit, cap: Capture, shift_ms: int = 0) -> Tuple[Optional[Ctx], Optional[str]]:
    ts = cap.series.get(ex.ticker)
    if ts is None:
        return None, 'not_in_capture'
    t0 = ex.t0_ms + shift_ms
    i0 = ts.last_k_at_or_before(t0)
    if i0 < 0:
        return None, 'no_s0'
    m = cap.markets.get(ex.ticker)
    hg = HeldGrid(Grid.from_market(m), ex.side)
    s0 = ts.s[i0]
    hb0 = held_book(s0, ex.side)
    if not hb0.bids:
        return None, 'no_bid'
    return Ctx(ex, shift_ms, t0, t0 + PLACEMENT_SLACK_MS, ts, i0, s0, hb0, hg, close_ms(ex.ticker, m), kind_of(ex.ticker, m)), None


def usable(ctx: Ctx, h_s: int) -> Optional[str]:
    """Reason this event-horizon is dropped, or None. The same drops apply to every arm."""
    te = ctx.tp + h_s * 1000
    if ctx.t0 - ctx.s0.k > GAP_MS:
        return 'gap'
    ifb = ctx.ts.last_k_at_or_before(te)
    if ifb < ctx.i0 or te - ctx.ts.s[ifb].k > GAP_MS or ctx.ts.max_gap(ctx.i0, ifb) > GAP_MS:
        return 'gap'
    if ctx.close is None:
        return 'no_close'
    if te + NEAR_CLOSE_MS >= ctx.close:
        return 'near_close'
    return None


def first_passage(order: Order, ctx: Ctx, ev: List[Sample]) -> Passage:
    n = ctx.ex.count
    thr = order.q + ctx.hg.up(order.q)
    a0 = ctx.hb0.asks[0][0]
    prev = ctx.tp
    strict = touch = None
    cleared = None
    for j, s in enumerate(ev):
        hb = held_book(s, ctx.ex.side)
        if hb.bids:
            b = hb.bids[0][0]
            if b >= order.q and touch is None:
                touch = Hit(s.k, prev, min(n, sum(z for p, z in hb.bids if p >= order.q)), j == 0)
            if b >= thr and strict is None:
                strict = Hit(s.k, prev, min(n, sum(z for p, z in hb.bids if p >= thr)), j == 0)
        if cleared is None and (not hb.asks or hb.asks[0][0] > a0):
            cleared = s.k
        prev = s.t
        if strict is not None:
            break
    return Passage(strict, touch, cleared)


@dataclass
class Arm:
    proceeds: float
    fee0: float          # maker fee multiplier 0 (published)
    fee1: float          # maker fee multiplier 1 (stress)
    short: float
    filled: float = 0.0                # contracts sold in total (resting fill plus fallback)
    rest_filled: float = 0.0           # contracts the resting order is credited with
    delay_ms: Optional[int] = None     # first evidence sample showing the fill, from the decision (an upper bound)
    bracket_ms: Optional[int] = None   # width of the interval the fill is known to lie in
    pre_cross: bool = False
    ambiguous: bool = False
    q_u: Optional[int] = None
    queue: Optional[float] = None

    @property
    def net0(self) -> float:
        return self.proceeds - self.fee0

    @property
    def net1(self) -> float:
        return self.proceeds - self.fee1


def _fallback(ctx: Ctx, fb: Sample, rem: float) -> Walk:
    if rem <= 1e-9:
        return Walk(0.0, 0.0, 0.0, 0.0)
    hb = held_book(fb, ctx.ex.side)
    if not hb.bids:
        return Walk(0.0, 0.0, 0.0, rem)
    return walk_ioc(hb.bids, rem, ioc_floor(hb.bids[0][0], ctx.hg))


def ioc_now(ctx: Ctx) -> Arm:
    w = walk_ioc(ctx.hb0.bids, ctx.ex.count, ioc_floor(ctx.hb0.bids[0][0], ctx.hg))
    return Arm(w.proceeds, w.fee, w.fee, w.short, filled=w.sold)


def wait_arm(ctx: Ctx, h_s: int) -> Arm:
    fb = ctx.ts.s[ctx.ts.last_k_at_or_before(ctx.tp + h_s * 1000)]
    w = _fallback(ctx, fb, ctx.ex.count)
    return Arm(w.proceeds, w.fee, w.fee, w.short, filled=w.sold)


def rest_arm(ctx: Ctx, order: Order, ps: Passage, rule: str, h_s: int) -> Arm:
    te = ctx.tp + h_s * 1000
    fb = ctx.ts.s[ctx.ts.last_k_at_or_before(te)]
    hit = ps.strict if rule == 'strict' else ps.touch
    if hit is not None and hit.k > te:
        hit = None
    qd = order.q / UNIT
    filled = hit.qty if hit else 0.0
    f0 = f1 = 0.0
    pre = False
    if filled > 0:
        pre = hit.first
        if pre:
            f0 = f1 = float(taker_fee(filled, qd))
        else:
            f0, f1 = float(maker_fee(filled, qd, 0.0)), float(maker_fee(filled, qd, 1.0))
    w = _fallback(ctx, fb, ctx.ex.count - filled)
    strict_hit = ps.strict is not None and ps.strict.k <= te
    amb = ps.cleared_k is not None and ps.cleared_k <= te and not strict_hit
    return Arm(filled * qd + w.proceeds, f0 + w.fee, f1 + w.fee, w.short, filled=filled + w.sold, rest_filled=filled,
               delay_ms=(hit.k - ctx.t0) if hit else None, bracket_ms=(hit.k - hit.prev_t) if hit else None,
               pre_cross=pre, ambiguous=amb, q_u=order.q, queue=order.queue)


def evaluate(ctx: Ctx, h_s: int, variants=VARIANTS) -> Dict[object, Optional[Arm]]:
    """Every arm for one event-horizon: 'ioc', 'wait', and (variant, rule) -> Arm or None when the variant is n/a."""
    te = ctx.tp + h_s * 1000
    ev = ctx.ts.evidence(ctx.tp, te)
    out: Dict[object, Optional[Arm]] = {'ioc': ioc_now(ctx), 'wait': wait_arm(ctx, h_s)}
    for v in variants:
        order = place(v, ctx.hb0, ctx.hg, ctx.ex.ref_bid_u)
        ps = first_passage(order, ctx, ev) if order else None
        for rule in ('strict', 'touch'):
            out[(v, rule)] = rest_arm(ctx, order, ps, rule, h_s) if order else None
    return out
