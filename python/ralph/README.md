# Ralph profit loop — implementation bootstrap

This directory is research and control-plane code, not a trading strategy. It never imports the Kalshi order client, deploys a bot, starts a model, reads Lightsail, or changes a heat curve.

## Architecture

- Full queue and directional rules: docs/ralph/ledger.md.
- Durable machine ledger: separate ralph-state Git branch, at ralph/ledger.json; never main. Its ralph/STOP file currently prevents queue mutations.
- python/ralph/control.py: local-only fail-closed queue state machine with legal transitions, three maker rounds, a local exclusive writer, STOP, monotonic trial counts, risk escalation, critic checks, and stage token ceilings. A future remote workflow must add GitHub Actions concurrency and SHA compare-and-swap on the state branch: the local file lock is not a remote distributed lease.
- j06_window.py, j06_rollup.py, j22_scoreboard.py and window_core.py are diagnostics, not the protected grader. Source of truth for the current 60-second one-test definition: research/heatmap_live/score.ts. Independent parity required before binding use.
- Job cards: docs/ralph/J22_J06_JOB_CARDS.md. Critic rubric: docs/ralph/CRITIC_PROMPTS_AND_RUBRIC.md.
- A protected deterministic evaluator and pinned policy must be maintained separately in python/ralph_eval/ and ralph/pins.json; they are deliberately NOT created by this maker patch.

## Local-only verification

From repository root, Python 3.11+:

    PYTHONPATH=python python3 -m unittest discover -s python/ralph/tests -v

To inspect the state from an isolated worktree:

    git worktree add ../coinbaseTraderBot-ralph-state ralph-state
    PYTHONPATH=python python3 -m ralph.control --ledger ../coinbaseTraderBot-ralph-state/ralph/ledger.json status

Do not delete ralph/STOP while the grader, pins, review, and remote lease protocol are incomplete. The code does not trigger trading orders or background jobs.

## Private data and evidence

J06 requires private normalized heat-call JSONL, contract metadata, and actual timestamped two-sided Kalshi books, covering the sellable bid window through its deadline. Historical Binance spot bars, settlements, or synthetic books cannot establish a fee-net Kalshi profit window. The live reader writes daily calls (python/heat_reader/reader.py), and the private trip pipeline (python/lossreview/builder.py) separates ex-ante from outcome columns (python/lossreview/schema.py). Do not place private per-trade data, tickers with trade P&L, or paths to private files on public GitHub.

J22 requires the first predeclared 12 consecutive FULL-book forward UTC days on one frozen candidate, with a one-day embargo and one planned look. J06 August 1–November 4, 2026 historical contract evidence is blocked until actual book coverage is verified. Unavailable evidence is neither a passing nor a failing trade.

## Safety and owner decisions

No heat-curve edits, live-mode changes, deployment, direct push to main, order-flow changes, automatic pool steps, or evaluator self-edits. No model can mark a job passed. The owner approved Binance data for live use, but this does not itself enable trading or independently verify provider terms. Claude's weekly limit is not a limit on ChatGPT's work; unconfigured token budgets for future external autonomous model dispatch remain fail-closed.
