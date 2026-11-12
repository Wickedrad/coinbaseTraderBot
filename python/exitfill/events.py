"""The paper exits to replay. exits.csv carries only what the fill question needs: no entry price, no profit, no strike."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import List, Optional

from . import UNIT
from .guard import check_ticker, check_ts

COLUMNS = ['n', 'ticker', 'side', 'exit_event', 't0_ms', 't0_src', 'count', 'ref_bid', 'limit_px']
EXIT_EVENTS = ('plan_ratchet_sell', 'other_sale')


@dataclass(frozen=True)
class Exit:
    n: int
    ticker: str
    side: str                  # held side: yes or no
    exit_event: str            # plan_ratchet_sell or other_sale
    t0_ms: int                 # the sale decision (plan event time) or the closed record time for other_sale
    t0_src: str                # plan_at or closed_utc
    count: float               # contracts the sale event sold
    ref_bid_u: Optional[int]   # the held-side bid the bot saw at the decision (ratchet only)
    limit_u: Optional[int]

    @property
    def etype(self) -> str:
        return 'ratchet' if self.exit_event == 'plan_ratchet_sell' else 'other_sale'


def _u(s: str) -> Optional[int]:
    s = (s or '').strip()
    return int(round(float(s) * UNIT)) if s else None


def load_exits(path: str) -> List[Exit]:
    out: List[Exit] = []
    with open(path, newline='', encoding='utf-8') as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames != COLUMNS:
            raise ValueError(f'exits.csv columns must be exactly {COLUMNS}')
        for r in rd:
            ticker = r['ticker'].strip()
            check_ticker(ticker)
            if r['side'] not in ('yes', 'no'):
                raise ValueError(f"side must be yes or no: row {r['n']}")
            if r['exit_event'] not in EXIT_EVENTS:
                raise ValueError(f"unknown exit_event: row {r['n']}")
            t0 = int(r['t0_ms'])
            check_ts(t0, f"exit {r['n']} t0")
            cnt = float(r['count'])
            if not cnt > 0:
                raise ValueError(f"count must be positive: row {r['n']}")
            out.append(Exit(int(r['n']), ticker, r['side'], r['exit_event'], t0, r['t0_src'], cnt, _u(r['ref_bid']), _u(r['limit_px'])))
    return out
