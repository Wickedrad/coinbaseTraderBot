"""The card: aggregates only (no ticker, no per-event time, no per-event row). Every number is a measurement with its n,
k and a descriptive interval; nothing here is a threshold or a verdict."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import BOOT_N, BOOT_SEED, HORIZONS_S, OTHER_T0_SHIFTS_MS, PRIMARY, T0_SHIFTS_MS, VARIANTS

CAVEATS = {
    'C1': 'Books are sampled about every 10 s with the top 3 levels. A touch between samples is missed, so fills are undercounted.',
    'C2': 'No trade prints exist in the capture. A cancel and a trade look the same; the ambiguous count is shown and never credited.',
    'C3': 'Our own order moves nothing and nobody reacts to it. FIFO priority is assumed and unverified on live fills.',
    'C4': 'One overnight of thin US hours, all coins moving together. n is small and the bootstrap SE (15-minute blocks) is only descriptive.',
    'C5': 'Maker fee 0 on these series is the published value, unconfirmed on live fills. The stress column charges the full maker rate.',
    'C6': 'A resting fill is a rebound; holding was better afterwards by construction. Read the price effect against the wait-only column.',
    'C7': 'For other_sale the exit type is an inference (hold exit or pacer snipe) and t0 is the closed record time, within about 1 to 2 s of the decision either way. Its shifts are shown.',
    'C8': 'A reduce-only resting order and the cancel-then-IOC race (double sell) are not modelled.',
    'C9': 'Runner clock versus bot clock offset is unknown. The clock-shift table shows how much the headline cell moves with it.',
    'C10': 'The grid has many cells on correlated events; the extremes of a noisy grid are selected. Only the headline cell was declared in advance.',
    'C11': 'The 1 s placement slack is a modelling assumption, not a measured latency. The model sell-now arm is an optimistic reference: it fills instantly on a snapshot.',
    'C12': 'Contracts the stored levels cannot absorb, or that meet no bid at the fallback, earn zero in EVERY arm and are counted; the depth-matched column drops those events and that choice depends on the future.',
}


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mean_se(vals: Sequence[float], blocks: Sequence[int]) -> Tuple[float, float]:
    """Mean and a block-bootstrap SE (resampling whole 15-minute blocks, so coins moving together stay together)."""
    if not len(vals):
        return (float('nan'), float('nan'))
    v, b = np.asarray(vals, dtype=float), np.asarray(blocks)
    ub, inv = np.unique(b, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=v), np.bincount(inv).astype(float)
    if len(ub) < 2:
        return (float(v.mean()), float('nan'))
    rng = np.random.RandomState(BOOT_SEED)
    idx = rng.randint(0, len(ub), size=(BOOT_N, len(ub)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return (float(v.mean()), float(means.std(ddof=1)))


def fmt_pm(m: float, se: float, nd: int = 2) -> str:
    if m != m:
        return 'n/a'
    return f'{m:+.{nd}f}' + (f' ±{se:.{nd}f}' if se == se else ' ±n/a')


def fmt_share(k: int, n: int) -> str:
    if n <= 0:
        return 'n/a'
    lo, hi = wilson(k, n)
    return f'{k}/{n} = {100 * k / n:.0f}% [{100 * lo:.0f}, {100 * hi:.0f}]'


def flags(n: int, k: Optional[int] = None, short: int = 0) -> str:
    out = []
    if n < 30:
        out.append('n<30')
    if k is not None and k < 10:
        out.append('k<10')
    if short:
        out.append('short')
    return ' '.join(out) or '-'


def table(header: List[str], rows: List[List[str]]) -> str:
    out = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join(['---'] * len(header)) + '|']
    out += ['| ' + ' | '.join(r) + ' |' for r in rows]
    return '\n'.join(out)


# ---- aggregation over the per-event rows built by run.py -------------------------------------------------------
# A row is a dict: etype, kind, block, shift, H, reason (None when usable), n_contracts, s0_age_ms, ref_diff_ticks,
# arms {'ioc','wait',(variant, rule)}.

def _pick(rows, etype, shift, h):
    return [r for r in rows if r['etype'] == etype and r['shift'] == shift and r['H'] == h and r['reason'] is None]


def fill_stats(rows, etype, shift, h, variant, rule):
    pop = _pick(rows, etype, shift, h)
    elig = [r for r in pop if r['arms'].get((variant, rule)) is not None]
    arms = [r['arms'][(variant, rule)] for r in elig]
    k = sum(1 for a in arms if a.rest_filled > 0)
    contracts = sum(r['n_contracts'] for r in elig)
    return {'pop': pop, 'elig': elig, 'arms': arms, 'k': k, 'n': len(elig),
            'cw': (sum(a.rest_filled for a in arms) / contracts) if contracts else float('nan'),
            'amb': sum(1 for a in arms if a.ambiguous), 'pre': sum(1 for a in arms if a.rest_filled > 0 and a.pre_cross)}


def delta_stats(rows, etype, shift, h, variant, rule):
    """Dollars per exit versus selling now. 'All events' counts a variant that is not available as selling now."""
    pop = _pick(rows, etype, shift, h)
    d_now, d_wait, d_stress, fee_eff, price_eff, cents = [], [], [], [], [], []
    blocks, ok_d, ok_b, short_ev = [], [], [], 0
    for r in pop:
        a = r['arms'].get((variant, rule)) or r['arms']['ioc']
        i, w = r['arms']['ioc'], r['arms']['wait']
        d = a.net0 - i.net0
        d_now.append(d)
        d_wait.append(a.net0 - w.net0)
        d_stress.append(a.net1 - i.net0)
        fee_eff.append(i.fee0 - a.fee0)
        price_eff.append(a.proceeds - i.proceeds)
        cents.append(100 * d / r['n_contracts'])
        blocks.append(r['block'])
        short_ev += int(a.short > 1e-9)
        if a.short <= 1e-9 and i.short <= 1e-9 and w.short <= 1e-9:
            ok_d.append(d)
            ok_b.append(r['block'])
    return {'n': len(pop), 'blocks': blocks, 'now': d_now, 'wait': d_wait, 'stress': d_stress, 'fee': fee_eff,
            'price': price_eff, 'cents': cents, 'ok': ok_d, 'ok_blocks': ok_b, 'short_ev': short_ev}


def _cell(vals, blocks, nd=2):
    m, se = mean_se(vals, blocks)
    return fmt_pm(m, se, nd)


def coverage_block(cov, rows) -> str:
    t = table(['stage', 'ratchet', 'other_sale'], [[s, str(cov[s]['ratchet']), str(cov[s]['other_sale'])] for s in cov])
    drop = {}
    for r in rows:
        if r['shift'] == 0 and r['reason']:
            drop[(r['etype'], r['H'], r['reason'])] = drop.get((r['etype'], r['H'], r['reason']), 0) + 1
    d = table(['dropped', 'horizon s', 'ratchet', 'other_sale'],
              [[reason, str(h), str(drop.get(('ratchet', h, reason), 0)), str(drop.get(('other_sale', h, reason), 0))]
               for h in HORIZONS_S for reason in sorted({k[2] for k in drop})])
    return t + '\n\n' + (d if drop else 'No event-horizon was dropped.')


def calib_block(rows) -> str:
    base = [r for r in rows if r['shift'] == 0 and r['H'] == HORIZONS_S[1] and r['reason'] is None]
    out = []
    ages = [r['s0_age_ms'] for r in base]
    for etype in ('ratchet', 'other_sale'):
        a = [r['s0_age_ms'] for r in base if r['etype'] == etype]
        bins = [('<=5 s', lambda x: x <= 5000), ('5-10 s', lambda x: 5000 < x <= 10000), ('10-25 s', lambda x: x > 10000)]
        out.append([etype, 'book age at the decision'] + [str(sum(1 for x in a if f(x))) for _, f in bins])
    t1 = table(['exits', 'measure', '<=5 s', '5-10 s', '10-25 s'], out)
    diffs = [r['ref_diff_ticks'] for r in base if r['etype'] == 'ratchet' and r['ref_diff_ticks'] is not None]
    bins = [('below by 3+ ticks', lambda x: x <= -3), ('below by 1-2', lambda x: -3 < x < 0), ('equal', lambda x: x == 0),
            ('above by 1-2', lambda x: 0 < x < 3), ('above by 3+', lambda x: x >= 3)]
    t2 = table(['ratchet: sampled held bid minus the bid the bot logged'] + [b for b, _ in bins],
               [['events'] + [str(sum(1 for x in diffs if f(x))) for _, f in bins]])
    ioc_fee = sum(r['arms']['ioc'].fee0 for r in base if r['etype'] == 'ratchet')
    ioc_short = sum(1 for r in base if r['etype'] == 'ratchet' and r['arms']['ioc'].short > 1e-9)
    nrat = sum(1 for r in base if r['etype'] == 'ratchet')
    return t1 + '\n\n' + t2 + f'\n\nModel sell-now exit fees on the {nrat} usable ratchet exits (60 s horizon set): ${ioc_fee:.2f}. ' \
        f'Events where the 3 stored levels could not absorb the full size: {ioc_short} of {nrat}.'


def fills_grid(rows, etype, shift=0) -> str:
    out = []
    for v in VARIANTS:
        for h in HORIZONS_S:
            for rule in ('strict', 'touch'):
                s = fill_stats(rows, etype, shift, h, v, rule)
                delays = [a.delay_ms for a in s['arms'] if a.rest_filled > 0 and a.delay_ms is not None]
                bk = [sum(1 for d in delays if lo < d <= hi) for lo, hi in ((-10**9, 10000), (10000, 20000), (20000, 40000), (40000, 80000), (80000, 10**9))]
                cmax = [len(s['pop']) - s['n']]
                out.append([v, str(h), rule, str(len(s['pop'])), fmt_share(s['k'], s['n']),
                            f"{100 * s['cw']:.0f}%" if s['cw'] == s['cw'] else 'n/a',
                            str(s['amb']) if rule == 'strict' else '-', str(s['pre']), ' / '.join(map(str, bk)),
                            str(cmax[0]), flags(s['n'], s['k'])])
    return table(['variant', 'H s', 'rule', 'usable', 'filled k/n [95% CI]', 'contracts filled', 'ambiguous', 'seen in 1st sample',
                  'fill seen <=10/20/40/80/more s', 'variant n/a', 'flags'], out)


def delta_grid(rows, etype, shift=0) -> str:
    out = []
    for v in VARIANTS:
        for h in HORIZONS_S:
            for rule in ('strict', 'touch'):
                d = delta_stats(rows, etype, shift, h, v, rule)
                if not d['n']:
                    continue
                out.append([v, str(h), rule, str(d['n']), _cell(d['now'], d['blocks']), _cell(d['fee'], d['blocks']),
                            _cell(d['price'], d['blocks']), _cell(d['wait'], d['blocks']), _cell(d['stress'], d['blocks']),
                            _cell(d['cents'], d['blocks'], 1), f"{len(d['ok'])}: {_cell(d['ok'], d['ok_blocks'])}", str(d['short_ev']),
                            flags(d['n'], None, d['short_ev'])])
    return table(['variant', 'H s', 'rule', 'events', 'vs sell now $/exit', 'fee effect', 'price effect', 'vs wait only', 'vs now, maker fee x1',
                  'vs now c/contract', 'depth-matched n: vs now', 'unsold events', 'flags'], out)


def headline_block(rows) -> str:
    etype, variant, h, rule = PRIMARY
    f = fill_stats(rows, etype, 0, h, variant, rule)
    d = delta_stats(rows, etype, 0, h, variant, rule)
    wait_vs_now = [w - n for w, n in zip(
        [r['arms']['wait'].net0 for r in _pick(rows, etype, 0, h)], [r['arms']['ioc'].net0 for r in _pick(rows, etype, 0, h)])]
    t = table(['measure', 'value'], [
        ['usable ratchet exits', str(len(f['pop']))],
        ['variant available (inside the spread)', str(f['n'])],
        ['filled within the horizon (book-implied, stricter)', fmt_share(f['k'], f['n'])],
        ['contracts filled / contracts', f"{100 * f['cw']:.0f}%" if f['cw'] == f['cw'] else 'n/a'],
        ['ambiguous (ask cleared, bid never reached q)', str(f['amb'])],
        ['seen in the first sample (priced as taker)', str(f['pre'])],
        ['net vs selling now, $ per exit (all usable events, ±SE)', _cell(d['now'], d['blocks'])],
        ['  fee effect / price effect', _cell(d['fee'], d['blocks']) + ' / ' + _cell(d['price'], d['blocks'])],
        ['net vs waiting only, $ per exit', _cell(d['wait'], d['blocks'])],
        ['waiting only vs selling now, $ per exit', _cell(wait_vs_now, d['blocks'])],
        ['same, maker fee at full rate', _cell(d['stress'], d['blocks'])],
        ['same, depth-matched events (n)', f"{len(d['ok'])}: {_cell(d['ok'], d['ok_blocks'])}"],
        ['events with unsold contracts in this arm', str(d['short_ev'])],
    ])
    return f'Declared before the first run: **{etype}, {variant}, {h} s, strict.**\n\n' + t


def strata_block(rows) -> str:
    etype, variant, h, rule = PRIMARY
    pop = _pick(rows, etype, 0, h)
    def stratum(r):
        age = 'book <=10 s old' if r['s0_age_ms'] <= 10000 else 'book 10-25 s old'
        rd = r['ref_diff_ticks']
        pr = 'no logged bid' if rd is None else ('bid within 1 tick' if abs(rd) <= 1 else 'bid off by 2+ ticks')
        return age, pr
    keys = sorted({stratum(r) for r in pop})
    out = []
    for key in keys:
        sub = [r for r in pop if stratum(r) == key]
        elig = [r for r in sub if r['arms'].get((variant, rule)) is not None]
        k = sum(1 for r in elig if r['arms'][(variant, rule)].rest_filled > 0)
        dv = [(r['arms'].get((variant, rule)) or r['arms']['ioc']).net0 - r['arms']['ioc'].net0 for r in sub]
        out.append([key[0], key[1], str(len(sub)), fmt_share(k, len(elig)), _cell(dv, [r['block'] for r in sub]), flags(len(sub), k)])
    return table(['book age', 'logged bid vs sampled', 'events', 'filled k/n [CI]', 'vs sell now $/exit', 'flags'], out)


def shift_block(rows, etype, shifts) -> str:
    _, variant, h, rule = PRIMARY
    out = []
    for sh in shifts:
        f = fill_stats(rows, etype, sh, h, variant, rule)
        d = delta_stats(rows, etype, sh, h, variant, rule)
        out.append([f'{sh / 1000:+.0f} s', str(len(f['pop'])), fmt_share(f['k'], f['n']), _cell(d['now'], d['blocks']), flags(f['n'], f['k'])])
    return table(['decision time shifted by', 'usable', f'{variant} {h} s strict: filled k/n [CI]', 'vs sell now $/exit', 'flags'], out)


def render_card(meta: Dict[str, str], cov, rows) -> str:
    has_other = any(r['etype'] == 'other_sale' for r in rows)
    parts = [
        '# Heat exit-fill probe (research only; information)',
        f"Run {meta['run']} on this exit list · rules {meta['hash']} · read-log row {meta['readlog']} · window {meta['from']} to {meta['to']} · {meta['segments']} capture segments",
        'Question: had a SELL rested from the decision moment (plus a 1 s slack) instead of the reduce-only IOC at bid minus two ticks, '
        'would it have filled, how fast, at what price, and what would the fallback IOC cost? Fill evidence comes from sampled public YES books '
        '(book-implied; see the caveats). Dollars are net of exit fees only; the entry leg is identical in every arm.',
        '## Coverage (read this first)', coverage_block(cov, rows),
        '## Calibration', calib_block(rows),
        '## Headline cell', headline_block(rows),
        '## Ratchet exits: did the resting order fill', fills_grid(rows, 'ratchet'),
        '## Ratchet exits: dollars per exit versus selling now (all usable events; ±SE over 15-minute blocks)', delta_grid(rows, 'ratchet'),
        '## Headline cell by calibration class', strata_block(rows),
        '## Headline cell: clock shift of the decision time (C9)', shift_block(rows, 'ratchet', T0_SHIFTS_MS),
    ]
    if has_other:
        parts += ['## other_sale exits (type unknown, own block, never pooled with ratchet) (C7)',
                  fills_grid(rows, 'other_sale'), delta_grid(rows, 'other_sale'),
                  '### other_sale decision-time shifts', shift_block(rows, 'other_sale', OTHER_T0_SHIFTS_MS)]
    parts += ['## Caveats (apply to every table)'] + [f'- **{k}** {v}' for k, v in CAVEATS.items()]
    parts += ['Flags: n<30 or k<10 means the cell is too small to read; short means some contracts were unsold and valued at zero. '
              'Dollar differences are below the resolution of this sample unless the interval clearly excludes zero; the fill-count tables are the sturdier output.']
    return '\n\n'.join(parts) + '\n'
