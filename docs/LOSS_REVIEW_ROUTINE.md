# Loss review routine (the model steps of the daily loop)

Research only. This is the instruction a scheduled Claude routine follows each day; the mechanical stages are code
(`python/lossreview/daily.py`, no model tokens) and the model steps sit between them. Overview and rules of evidence:
`docs/LOSS_REVIEW.md`.

**When.** Daily at 21:00 UTC (4:00 PM EST), after `loss-review.yml` (it runs when the day's archive run completes, 20:30 UTC at
the latest) has put the previous UTC day's trip file on Drive. The archive's start time is GitHub's to choose (14:10 to 17:39 UTC
lately), so the routine does not assume which day is waiting: `daily pending` lists every day with a trip file and no `done`
marker, oldest first, and the routine runs steps 2 to 6 for each in order (the sweep's looks depend on day order) and then
`daily done DAY`. No pending day: it stops and says so in one line.

**Models and allowance** (the plan allowance, no overage credits; the weekly limit is the Opus audit's too):

| Step | Model | Per day |
| ---- | ----- | ------- |
| tags (`prepare-tags` batches of 25) | Haiku 5.5, one subagent per batch | up to 3 batches |
| hypotheses (one per loss class with 3 or more reviewed losers) | Sonnet 5.5 | up to 4 classes |
| adversary (one per validated hypothesis) | Sonnet 5.5 | up to 6 |
| weekly audit (Mondays): verdicts, registry, the week's defects | Opus 5.5, once | 1 |

Before each model step run `python3 -m lossreview.daily budget D --w W [--weekly N]` (the daily allowance is 600,000 tokens;
pass the weekly one when the plan's limit is near) and skip the model steps, not the mechanical ones, when it says `"ok": false`.
After each model step log it: `python3 -m lossreview.daily usage D --w W --step tag|hypothesize|adversary|audit --tokens-in N
--tokens-out N --items K` (the model and the prompt hash come from the step; the reply is what is left of the allowance).
Never use a model above Opus 5.5.

## Steps

Work folder `W` = a local copy of Drive `derived/loss-review` (files read and written through the Drive connector; the folder
holds per-trade rows, so it is never committed, posted or printed). Run from a checkout of the repository with
`PYTHONPATH=python`. Day `D` = each pending day, oldest first (`python3 -m lossreview.daily pending --w W`).

1. Fetch every `days/trips-*.jsonl` (with `registry.jsonl`, `usage.jsonl` and the existing `work/*/done.json`) into `W`; `pending` names the days still to do. Run the canary:
   `python3 -c "from lossreview import prompts; print(prompts.run_canary())"`; if it fails, stop: a validator is broken.
2. `python3 -m lossreview.daily prepare-tags D --w W`. For each `work/D/tag-NN.prompt.txt`, give the text to a Haiku subagent and
   save its reply, unchanged, as `tag-NN.response.json`. Then `apply-tags D`.
3. `prepare-hyp D`. For each `hyp-CLASS.prompt.txt`, a Sonnet call; save the reply as `hyp-CLASS.response.json`. Then `apply-hyp D`
   (validates every hypothesis: ex-ante columns only, closed lever set, at most 12 thresholds and 2 neighbors, at most 3 a class and 6 a
   day, unique ids, and no repeat of an idea already registered, refuted ones included; writes the adversary prompts with the blind
   winner control).
4. For each `adv-ID.prompt.txt`, a Sonnet call (it sees the hypothesis and aggregates only, never a ticker); save the reply as
   `adv-ID.response.json`. Then `apply-adv D` (registers survivors; every threshold and neighbor candidate counts as a trial).
5. `sweep D` (reads every open hypothesis at its next fixed look, 4, 8 or 12 scoring days after its generating losses, never
   nightly; freezes a candidate that survives BH over the registry, with the window's last day as `frozen_day`), then
   `shadow D` (counts only days after `frozen_day`, flags D's trips with every frozen rule, looks at 5 and 10 shadow days;
   a rule that is ready moves to `proposal`, one that is not ready by day 10 fades to `retired`), then `status`.
6. `done D`, then put `registry.jsonl`, `usage.jsonl` and `work/D/` back on Drive. Post at most one short message: counts only (reviewed
   losers, hypotheses admitted and refuted, candidates, shadow rules, rules ready for a PR, tokens used). No tickers, no
   per-trade values.
7. A rule that is `ready` is written up as a promotion PR in the style of the size dial (#346: off / log / on, a differential
   test that the heat curves' calls are identical with the rule on and off) and put to the owner; it is never merged by the
   routine. A curve edit (a rule on `rank`, `heat`, `weight`, `call_key`, ...) waits in `swept` until the owner says so.

## What the model steps must not do

- Free text is never a rule. Only a form that `forms.validate_hypothesis` accepts reaches the registry.
- Outcome columns are context, not features: the model sees them in a separate block and the validator refuses a hypothesis that
  names one.
- No claim of an effect: the sweep decides, from unseen days, against its placebo.
- The first dry night runs steps 2 to 5 once on the Nov 12 file and the result is read before the routine is scheduled.
