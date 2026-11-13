# Loss review routine (the model steps of the daily loop)

Research only. This is the instruction a scheduled Claude routine follows each day; the mechanical stages are code
(`python/lossreview/daily.py`, no model tokens) and the model steps sit between them. Overview and rules of evidence:
`docs/LOSS_REVIEW.md`.

**When.** Daily at 21:00 UTC (4:00 PM EST), after `loss-review.yml` (it runs when the day's archive run completes, 20:30 UTC at
the latest) has put the previous UTC day's trip file on Drive. The archive's start time is GitHub's to choose (14:10 to 17:39 UTC
lately), so the routine does not assume which day is waiting: `daily pending` lists every day with a trip file and no `done`
marker, oldest first, and the routine runs steps 2 to 4 for each in order (the sweep's looks depend on day order); step 4 ends with
`daily done DAY`. No pending day: it stops and says so in one line.

**Models and allowance** (the plan allowance, no overage credits; the weekly limit is the Opus audit's too):

| Step | Model | Per day |
| ---- | ----- | ------- |
| tags (`prepare-tags` batches of 25) | Haiku 5.5, one subagent per batch | up to 3 batches |
| hypotheses (one per loss class with 3 or more reviewed losers) | Sonnet 5.5 | up to 4 classes |
| adversary (one per validated hypothesis) | Sonnet 5.5 | up to 6 |
| weekly audit (Mondays): verdicts, registry, the week's defects | Opus 5.5, once | 1 |

Each dispatch below carries a `budget` stage before the next model step (the daily allowance is 600,000 tokens; a weekly limit is
checked the same way when the plan's limit is near) and a `usage` input that logs the step just done; when `budget` says
`"ok": false` the model steps are skipped and the day stays pending. Never use a model above Opus 5.5.

## How the routine reaches the data

| What | Where it runs | How |
| ---- | ------------- | --- |
| mechanical stages (code, no tokens) | GitHub runner, `.github/workflows/loss-review-stages.yml` | the routine dispatches it (GitHub `actions_run_trigger`, ref `main`) and reads the run's `LOSSLOOP` lines (`get_job_logs`) |
| per-trade files, prompts, registry, usage log | private Drive `derived/loss-review` | the runner pulls and puts them with rclone; the routine reads a prompt with the Drive connector (`search_files` by name, `read_file_content`) |
| model steps (Haiku, Sonnet, Opus) | the routine's subagents | each subagent is given the prompt file's name, reads it through the Drive connector and returns the JSON reply |
| model replies | the next dispatch's `responses` input | `{"tag-00": [...], "hyp-WRONG_SIDE": {...}, "adv-<id>": {...}}`, 60 KB at most per dispatch |

Why the replies travel in a dispatch input and not as files: the runner's Drive token (scope `drive.file`) sees only files it made
itself, and a file made by the connector is not one of them. A reply holds tags by index in a batch, hypothesis specs and adversary
verdicts, never a ticker or a time (the prompts show a trade by index only), so it may sit in the public repository's run record.
The prompts and the trip files do hold per-trade values: they stay on Drive and in the runner's temporary folder, and the job log
prints only what `daily.py` prints (counts, and dollar figures only for cells of 5 trips or more).

Stage inputs: `day` (UTC day), `stages` (in order, comma or space separated: `pending prepare-tags apply-tags prepare-hyp apply-hyp
apply-adv sweep shadow status budget window done`), `usage` (`step:tokens_in:tokens_out:items;...`, logged first), `responses`,
`since`/`until` (the window stage). Every run pulls the trip files, `registry.jsonl`, `usage.jsonl`, the done marks and the day's
work folder, runs the canary (a broken validator stops it before it writes anything), logs the usage, saves the responses, runs the
stages, and puts back only `registry.jsonl`, `usage.jsonl` and `work/DAY/`. A failed stage stops the run before the put.
Dispatch one run at a time and wait for it to finish (the workflow's concurrency group keeps a second one waiting, and a third
replaces the second).

## Steps

Day `D` = each pending day, oldest first.

1. Dispatch `day=<yesterday> stages=pending,status`. The `pending` line names the days still to do; none: stop and say so in one line.
   For each `D`, steps 2 to 4 (then 5 and 6); then the next day.
2. Dispatch `day=D stages=prepare-tags,budget`. If `budget` says `"ok": false`, leave `D` pending and stop (the mechanical stages
   only run next time). Else, for each `work/D/tag-NN.prompt.txt` (Drive connector), a Haiku subagent reads it and returns the JSON.
   Dispatch `day=D stages=apply-tags,prepare-hyp,budget responses={tag-NN: reply...} usage=tag:IN:OUT:ITEMS`.
3. For each `work/D/hyp-CLASS.prompt.txt`, a Sonnet subagent. Dispatch `day=D stages=apply-hyp,budget responses={hyp-CLASS: reply...}
   usage=hypothesize:IN:OUT:ITEMS` (`apply-hyp` validates every hypothesis: ex-ante columns only, closed lever set, at most 12
   thresholds and 2 neighbors, at most 3 a class and 6 a day, unique ids, and no repeat of an idea already registered, refuted ones
   included; it writes the adversary prompts with the blind winner control).
4. For each `work/D/adv-ID.prompt.txt`, a Sonnet subagent (it sees the hypothesis and aggregates only, never a ticker). Dispatch
   `day=D stages=apply-adv,sweep,shadow,status,done responses={adv-ID: reply...} usage=adversary:IN:OUT:ITEMS`:
   `apply-adv` registers survivors (every threshold and neighbor candidate counts as a trial); `sweep` reads every open hypothesis at
   its next fixed look, 4, 8 or 12 scoring days after its generating losses, never nightly, and freezes a candidate that survives
   BH over the registry, with the window's last day as `frozen_day`; `shadow` counts only days after `frozen_day`, flags D's trips
   with every frozen rule and looks at 5 and 10 shadow days (a rule that is ready moves to `proposal`, one that is not ready by day
   10 fades to `retired`); `done` marks the day.
5. Post at most one short message: counts only (reviewed losers, hypotheses admitted and refuted, candidates, shadow rules, rules
   ready for a PR, tokens used). No tickers, no per-trade values.
6. A rule that is `ready` is written up as a promotion PR in the style of the size dial (#346: off / log / on, a differential
   test that the heat curves' calls are identical with the rule on and off) and put to the owner; it is never merged by the
   routine. A curve edit (a rule on `rank`, `heat`, `weight`, `call_key`, ...) waits in `swept` until the owner says so.

A subagent token count that the tool does not report is estimated (prompt length / 4 in, reply length / 4 out) and logged as such.
The budget stage counts every logged step, so an under-count only makes the allowance look larger than it is: keep the estimate on
the high side.

To check that a day agrees with an earlier hand study, dispatch `stages=window since=00:00 until=HH:MM:SS`: the window's full
summary goes to `work/D/window-*.json` on Drive (read it with the connector); the log shows only the trip count.

## What the model steps must not do

- Free text is never a rule. Only a form that `forms.validate_hypothesis` accepts reaches the registry.
- Outcome columns are context, not features: the model sees them in a separate block and the validator refuses a hypothesis that
  names one.
- No claim of an effect: the sweep decides, from unseen days, against its placebo.
- The first dry night runs steps 2 to 4 once on the Nov 12 file and the result is read before the routine is scheduled.
