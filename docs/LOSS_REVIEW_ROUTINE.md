# Loss review routine (the model steps of the daily loop)

Research only. This is the instruction a scheduled Claude routine follows each day; the mechanical stages are code
(`python/lossreview/daily.py`, no model tokens) and the model steps sit between them. Overview and rules of evidence:
`docs/LOSS_REVIEW.md`.

**When.** Daily at 15:00 UTC (10:00 AM EST), after the health check (14:15 UTC) and after `loss-review.yml` (11:30 UTC) has put
the previous UTC day's trip file on Drive. A routine that finds no file for that day stops and says so in one line.

**Models and allowance** (the plan allowance, no overage credits; the weekly limit is the Opus audit's too):

| Step | Model | Per day |
| ---- | ----- | ------- |
| tags (`prepare-tags` batches of 25) | Haiku 5.5, one subagent per batch | up to 3 batches |
| hypotheses (one per loss class with 3 or more reviewed losers) | Sonnet 5.5 | up to 4 classes |
| adversary (one per validated hypothesis) | Sonnet 5.5 | up to 6 |
| weekly audit (Mondays): verdicts, registry, the week's defects | Opus 5.5, once | 1 |

Check `prompts.budget_check` against `usage.jsonl` before each model step: about 0.4 to 0.6 million tokens a day, and skip the
model steps (the mechanical stages still run) when the weekly limit is near. Log every model step with `prompts.usage_record`
(model, prompt hash, tokens, items). Never use a model above Opus 5.5.

## Steps

Work folder `W` = a local copy of Drive `derived/loss-review` (files read and written through the Drive connector; the folder
holds per-trade rows, so it is never committed, posted or printed). Run from a checkout of the repository with
`PYTHONPATH=python`. Day `D` = yesterday UTC.

1. Fetch `days/trips-D.jsonl` (and the other `days/trips-*.jsonl`, `registry.jsonl`, `usage.jsonl`) into `W`. Run the canary:
   `python3 -c "from lossreview import prompts; print(prompts.run_canary())"`; if it fails, stop: a validator is broken.
2. `python3 -m lossreview.daily prepare-tags D --w W`. For each `work/D/tag-NN.prompt.txt`, give the text to a Haiku subagent and
   save its reply, unchanged, as `tag-NN.response.json`. Then `apply-tags D`.
3. `prepare-hyp D`. For each `hyp-CLASS.prompt.txt`, a Sonnet call; save the reply as `hyp-CLASS.response.json`. Then `apply-hyp D`
   (validates every hypothesis: ex-ante columns only, closed lever set, at most 12 thresholds and 2 neighbors; writes the
   adversary prompts with the blind winner control).
4. For each `adv-ID.prompt.txt`, a Sonnet call (it sees the hypothesis and aggregates only, never a ticker); save the reply as
   `adv-ID.response.json`. Then `apply-adv D` (registers survivors; every threshold and neighbor candidate counts as a trial).
5. `sweep D` (reads every open hypothesis at its next fixed look, 4, 8 or 12 scoring days after its generating losses, never
   nightly; freezes a candidate that survives BH over the registry, with the window's last day as `frozen_day`), then
   `shadow D` (counts only days after `frozen_day`, flags D's trips with every frozen rule, looks at 5 and 10 shadow days;
   a rule that is ready moves to `proposal`, one that is not ready by day 10 fades to `retired`), then `status`.
6. Put `registry.jsonl`, `usage.jsonl` and `work/D/` back on Drive. Post at most one short message: counts only (reviewed
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
