"""Deterministic profit-plan gates. This module is PROTECTED, not for maker edits.

Public outputs contain aggregated day metrics only. An evaluator result is evidence,
not authorization to deploy, edit curves, change live mode, or promote a model.

The owner-supplied criteria are immutable pending explicit pin approval. Ambiguous
split rules are blocked rather than guessed. Each job/arm counts as a trial.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, mean, stdev
from typing import Any

ALPHA = 0.10
FDR_Q = 0.10
DAYS = 12
EMBARGO_DAYS = 1
DIRECTION_POSITIVE_DAYS = 9
TRIP_FLOOR = 0.85
PAPER_POOL_USD = 200.0
HARM_LOOKS = (4, 8)
LOOK_DAY = 12
NULL_STOP = 3
MAX_ROUNDS = 3


class InvalidEvidence(ValueError):
    pass


def finite(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise InvalidEvidence("expected finite numeric aggregate")
    return float(v)


def _beta_cf(a: float, b: float, x: float) -> float:
    # Continued fraction, Numerical Recipes; numerical input bounds checked by caller.
    tiny, eps = 1e-300, 3e-14
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            return h
    raise InvalidEvidence("beta fraction did not converge")


def _ibeta(a: float, b: float, x: float) -> float:
    if not (a > 0 and b > 0 and 0 <= x <= 1):
        raise InvalidEvidence("invalid beta arguments")
    if x == 0:
        return 0.0
    if x == 1:
        return 1.0
    k = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                 + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return k * _beta_cf(a, b, x) / a
    return 1.0 - k * _beta_cf(b, a, 1.0 - x) / b


def t_survival(t: float, df: int) -> float:
    """Exact one-sided Student-t upper tail from regularized incomplete beta."""
    finite(t)
    if df < 1:
        raise InvalidEvidence("insufficient degrees of freedom")
    half = 0.5 * _ibeta(df / 2.0, 0.5, df / (df + t * t))
    return max(0.0, min(1.0, half if t >= 0 else 1.0 - half))


def t_critical(alpha: float, df: int) -> float:
    if not 0 < alpha < 0.5:
        raise InvalidEvidence("invalid alpha")
    low, high = 0.0, 40.0
    for _ in range(100):
        mid = (low + high) / 2
        if t_survival(mid, df) > alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def one_sided_gap(xs: list[float]) -> dict:
    """Daily paired-gap t test. Days, not per-trade rows, are independent units."""
    n = len(xs)
    if n < 4:
        return {"n": n, "mean": None, "se": None, "p_one_sided": None}
    vals = [finite(x) for x in xs]
    m = mean(vals)
    sd = stdev(vals)
    se = sd / math.sqrt(n)
    p = t_survival(m / se, n - 1) if se > 0 else (0.0 if m > 0 else 1.0)
    return {"n": n, "mean": m, "se": se, "p_one_sided": p}


def independent_gap(a: list[float], b: list[float]) -> dict:
    """Difference of independent day means; 6-versus-6 alternating-day design."""
    if len(a) < 2 or len(b) < 2:
        return {"n": len(a) + len(b), "mean": None, "se": None, "p_one_sided": None}
    aa, bb = [finite(x) for x in a], [finite(x) for x in b]
    na, nb = len(aa), len(bb)
    pooled = ((na - 1) * stdev(aa) ** 2 + (nb - 1) * stdev(bb) ** 2) / (na + nb - 2)
    se = math.sqrt(pooled * (1 / na + 1 / nb))
    gap = mean(aa) - mean(bb)
    p = t_survival(gap / se, na + nb - 2) if se > 0 else (0.0 if gap > 0 else 1.0)
    return {"n": na + nb, "mean": gap, "se": se, "p_one_sided": p}


def bh_pass(p_values: list[float], q: float = FDR_Q) -> list[bool]:
    if not 0 < q < 1:
        raise InvalidEvidence("invalid FDR threshold")
    if any(not 0 <= finite(p) <= 1 for p in p_values):
        raise InvalidEvidence("invalid p value")
    ix = sorted(range(len(p_values)), key=lambda i: p_values[i])
    cut = -1
    for n, i in enumerate(ix, 1):
        if p_values[i] <= q * n / len(ix):
            cut = n
    passed = [False] * len(ix)
    for i in ix[:max(0, cut)]:
        passed[i] = True
    return passed


def mde(sd_daily: float, *, design: str = "paired", power: float = 0.80) -> float:
    """Approximate one-sided 10% / 80%-power MDE, t critical + z power.

    Paired: 12 same-day daily differences. Alternating: 6 vs 6 whole days.
    This reproduces the brief's approx $64/$128 at $100 daily SD.
    """
    sd = finite(sd_daily)
    if sd <= 0 or not 0.5 < power < 1:
        raise InvalidEvidence("invalid MDE inputs")
    z = NormalDist().inv_cdf(power)
    if design == "paired":
        return (t_critical(ALPHA, DAYS - 1) + z) * sd / math.sqrt(DAYS)
    if design == "alternating":
        return (t_critical(ALPHA, DAYS - 2) + z) * sd * math.sqrt(2 / 6)
    raise InvalidEvidence("unknown arm design")


def _distinct_consecutive_utc(days: list[str]) -> bool:
    from datetime import date, timedelta
    try:
        xs = [date.fromisoformat(x) for x in days]
    except (ValueError, TypeError) as exc:
        raise InvalidEvidence("invalid UTC day") from exc
    return len(xs) == len(set(xs)) and all(xs[i] + timedelta(days=1) == xs[i + 1]
                                               for i in range(len(xs) - 1))


def direction_gate(rows: list[dict], *, signed: bool, negative_splits_rule_pinned: bool,
                   slot_gap: float | None = None, slot_se: float | None = None,
                   negative_splits_clear: bool | None = None) -> dict:
    """Stage D: binding only when quote coverage, splits, and signatures are pinned.

    rows are 12 precommitted chronological FULL-book day aggregates, each with
    day, full_book, called_windows, opposite_windows, n, source_mode=forward.
    This is a period check. The independent J06 all-history result also needs
    its own paired-slot SE; callers must provide that evidence separately.
    """
    if len(rows) != DAYS or not _distinct_consecutive_utc([r.get("day") for r in rows]):
        return {"status": "underpowered", "reason": "requires 12 fixed consecutive UTC days"}
    if any(r.get("source_mode") != "forward" or r.get("full_book") is not True for r in rows):
        return {"status": "blocked", "reason": "missing forward full-book coverage"}
    rates = []
    for r in rows:
        n = finite(r.get("n"))
        called, opposite = finite(r.get("called_windows")), finite(r.get("opposite_windows"))
        if n < 1 or int(n) != n or min(called, opposite) < 0 or max(called, opposite) > n:
            raise InvalidEvidence("invalid daily window counts")
        rates.append((called - opposite) / (2 * n))
    positive = sum(x > 0 for x in rates)
    score = one_sided_gap(rates)
    # Daily t test is diagnostic; the binding "one test" uses slot-clustered SE.
    out = {"status": "blocked", "positive_days": positive, "required": 9,
           "day_gap": score, "slot_gap": slot_gap, "slot_se": slot_se,
           "trial_count": 1}
    if positive < DIRECTION_POSITIVE_DAYS:
        out.update(status="iterate", reason="fewer than 9 positive daily gaps")
    elif not negative_splits_rule_pinned:
        out.update(reason="coin/side negative split rule not pinned")
    elif not signed:
        out.update(reason="Stage D not independently signed")
    elif slot_gap is None or slot_se is None or negative_splits_clear is None:
        out.update(reason="missing signed slot-clustered score or split verdict")
    elif finite(slot_se) <= 0 or finite(slot_gap) < 2 * finite(slot_se):
        out.update(status="iterate", reason="direction gap below 2 x clustered SE")
    elif not negative_splits_clear:
        out.update(status="iterate", reason="coin or side clearly negative")
    else:
        out.update(status="conditional", reason="Stage D numeric conditions met; no automatic promotion")
    return out


def execution_gate(arms: list[dict], *, direction_signed: bool, look_day: int,
                   embargo_verified: bool, trial_count: int) -> dict:
    """Stage 1 per-lever day-12 gate; one result per arm on a frozen config.

    Each arm: id, design paired/alternating, gaps = 12 chronological daily
    net differences, baseline_decisions, arm_decisions, placebo_gap,
    measured_sd, conservative_ceiling, full_book_days, frozen, count_in_ledger.
    Missing/mixed arms are blocked. Numerical pass is code-only, never a model.
    """
    if not direction_signed:
        return {"status": "blocked", "reason": "no signed direction Stage D"}
    if look_day not in (4, 8, 12) or not embargo_verified:
        return {"status": "blocked", "reason": "invalid look or missing embargo"}
    if trial_count < len(arms) or not arms:
        return {"status": "blocked", "reason": "all tested arms must count as trials"}
    outcomes = []
    for arm in arms:
        if not arm.get("frozen") or not arm.get("count_in_ledger"):
            raise InvalidEvidence("unregistered or unfrozen arm")
        book_days = arm.get("full_book_days", [])
        if len(book_days) < look_day:
            outcomes.append({"id": arm.get("id"), "status": "underpowered"})
            continue
        if not _distinct_consecutive_utc(book_days[:look_day]):
            outcomes.append({"id": arm.get("id"), "status": "blocked", "reason": "nonconsecutive full-book days"})
            continue
        design = arm.get("design")
        if design == "paired":
            gaps = arm.get("gaps", [])
            if len(gaps) < look_day:
                outcomes.append({"id": arm.get("id"), "status": "underpowered"})
                continue
            score = one_sided_gap([finite(x) for x in gaps[:look_day]])
        elif design == "alternating":
            # Pre-registered alternation: half the days on the arm, half on control.
            a, b = arm.get("arm_day_net", []), arm.get("control_day_net", [])
            if look_day % 2 or len(a) < look_day // 2 or len(b) < look_day // 2:
                outcomes.append({"id": arm.get("id"), "status": "underpowered"})
                continue
            score = independent_gap(a[:look_day // 2], b[:look_day // 2])
        else:
            raise InvalidEvidence("arm design must be paired or alternating")
        if look_day in HARM_LOOKS:
            harm = score["se"] is not None and score["mean"] < -2 * score["se"]
            outcomes.append({"id": arm["id"], "status": "harm_stop" if harm else "awaiting_look",
                             "days": look_day, "gap": score})
            continue
        md = mde(arm["measured_sd"], design=arm["design"])
        if finite(arm["conservative_ceiling"]) < md:
            outcomes.append({"id": arm["id"], "status": "underpowered", "mde": md,
                             "reason": "ceiling below MDE", "gap": score})
            continue
        baseline, decisions = finite(arm["baseline_decisions"]), finite(arm["arm_decisions"])
        if baseline <= 0 or decisions < TRIP_FLOOR * baseline:
            outcomes.append({"id": arm["id"], "status": "iterate", "mde": md,
                             "reason": "trips per hour below 85%", "gap": score})
            continue
        pg = finite(arm["placebo_gap"])
        if score["mean"] <= 0 or pg >= score["mean"] / 2:
            outcomes.append({"id": arm["id"], "status": "iterate", "mde": md,
                             "reason": "nonpositive gap or placebo reaches half", "gap": score})
            continue
        outcomes.append({"id": arm["id"], "status": "eligible", "mde": md,
                         "gap": score})
    # Family is ALL registered/scored arms on this look; no excluding losing p values.
    if look_day == LOOK_DAY:
        ps = [x["gap"]["p_one_sided"] if x.get("gap", {}).get("p_one_sided") is not None else 1.0
              for x in outcomes]
        for x, accepted in zip(outcomes, bh_pass(ps)):
            if x["status"] == "eligible":
                x["status"] = "conditional" if accepted else "iterate"
                x["reason"] = "BH q=0.10 met; owner approval pending" if accepted else "BH q=0.10 not met"
    return {"status": "review", "look_day": look_day, "trial_count": trial_count,
            "alpha_one_sided": ALPHA, "bh_q": FDR_Q, "arms": outcomes}


def stage1_paper_gate(days: list[dict], *, signed_direction: bool,
                      fresh_config: bool, look_day: int = LOOK_DAY) -> dict:
    """Only positive *net after fees* against total money put in, no refills.

    Not a confirmed profitability proof. Distinguish real account cash from P&L.
    """
    if not signed_direction or not fresh_config:
        return {"status": "blocked", "reason": "unsigned direction or changed config"}
    if look_day != LOOK_DAY or len(days) != DAYS or not _distinct_consecutive_utc([x.get("day") for x in days]):
        return {"status": "underpowered", "reason": "one fixed day-12 look required"}
    for x in days:
        if x.get("full_book") is not True or x.get("autorefills") != 0:
            return {"status": "blocked", "reason": "missing book or paper refill"}
    if any(x.get("pool_exhausted") for x in days):
        return {"status": "blocked", "reason": "pool exhausted before look"}
    first = days[0]
    if finite(first.get("initial_pool")) != PAPER_POOL_USD:
        return {"status": "blocked", "reason": "paper initial pool not $200"}
    if any(finite(x.get("baseline_decisions")) <= 0 or
           finite(x.get("arm_decisions")) < TRIP_FLOOR * finite(x.get("baseline_decisions")) for x in days):
        return {"status": "iterate", "reason": "trading floor not maintained"}
    # reconciled_net already subtracts fees and funds put in, not displayed balance
    daily = [finite(x.get("reconciled_net")) for x in days]
    return {"status": "conditional" if sum(daily) > 0 else "iterate",
            "reason": "positive 12-day paper net; not profit proof" if sum(daily) > 0 else "nonpositive paper net",
            "days": DAYS, "net_after_fees": sum(daily), "min_trips_fraction": TRIP_FLOOR}