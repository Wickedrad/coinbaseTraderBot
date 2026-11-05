"""All-pairs entry/exit payoff matrices for Kalshi 15-minute and hourly contracts.

Every entry minute i against every later exit minute j (and settlement), net of Kalshi's real fees, with maker and
taker fills; a Longstaff-Schwartz / Snell-envelope exit policy learned from those matrices; entry labels that follow
that exit policy (never the best exit in hindsight); purged walk-forward validation, a deflated Sharpe gate and
placebo controls. See python/allpairs/README.md.
"""

# Steven, 2026-11-05 13:26 UTC: "for now let's not use DOGE at all". Enforced in data loading, whatever is passed.
EXCLUDED_ASSETS = frozenset({'DOGE'})
DEFAULT_ASSETS = ('BTC', 'ETH', 'SOL', 'XRP')
