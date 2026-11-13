# Loss review routine (the model steps of the daily loop)

Research only. This is the instruction a scheduled Claude routine follows each day; the mechanical stages are code
(`python/lossreview/daily.py`, no model tokens) and the model steps sit between them. Overview and rules of evidence:
`docs/LOSS_REVIEW.md`.

**When.** Daily at 21:00 UTC (4:00 PM EST), after `loss-review.yml` (it runs when the day's archive run completes, 20:30 UTC at
the latest) has put the previous UTC day's trip file on Drive. The archive's start time is GitHub's to choose (14:10 to 17:39 UTC
lately), so the routine does not assume which day is waiting: `daily pending` lists every day with a trip file and no `done`
marker, oldest first, and the routine runs steps 2 to 5 for each in order (the sweep's looks depend on day order); step 5 ends with
`daily done DAY`. No pending day: it stops and says so in one line.

**Models and allowance** (the plan allowance, no overage credits):

| Step | Model | Per day |
| ---- | ----- | ------- |
| tags (`prepare-tags` batches of 25) | Haiku 5.5, one subagent per batch | up to 3 batches |
| hypotheses (one per loss class with 3 or more reviewed losers) | Sonnet 5.5 | the 4 costliest classes |
| adversary (one per validated hypothesis) | Sonnet 5.5 | up to 6 |

The weekly Opus 5.5 audit (the prompt and the usage step exist: `prompts.build_audit_prompt`, step `audit`) is **not wired into the
stages yet**: there is no stage that writes its prompt or takes its reply, so the routine does not run it and Opus is not used
until it is built.

The allowance is per calendar day, counted on the day the tokens are spent (UTC today), not the day of the trips: a day that
ran out of allowance is picked up the next day with a fresh one. Each dispatch below carries a `budget` stage before the next
model step (daily allowance 600,000 tokens; pass `weekly=N` when the plan's weekly limit is near and it is checked too) and a
`usage` input that logs the step just done, once per workflow run (a re-run of the same run does not count it twice). When
`budget` says `"ok": false` the model steps stop and the day stays pending where it is. Never use a model above Opus 5.5.

## How the routine reaches the data

| What | Where it runs | How |
| ---- | ------------- | --- |
| mechanical stages (code, no tokens) | GitHub runner, `.github/workflows/loss-review-stages.yml` | the routine dispatches it (GitHub `actions_run_trigger`, ref `main`) and reads the run's `LOSSLOOP` lines (`get_job_logs`) |
| per-trade files, prompts, registry, usage log | private Drive `derived/loss-review` | the runner pulls and puts them with rclone; the routine reads a prompt with the Drive connector |
| model steps (Haiku, Sonnet) | the routine's subagents | each subagent is given the id of the prompt file, reads it through the Drive connector and returns the JSON reply |
| model replies | the next dispatch's `responses` input | `{"tag-00": [...], "hyp-WRONG_SIDE": [...], "adv-<id>": {...}}`, 60 KB at most per dispatch |

Why the replies travel in a dispatch input and not as files: the runner's Drive token (scope `drive.file`) sees only files it made
itself, and a file made by the connector is not one of them. A dispatch input is **public the moment it is sent**, and the prompts
show a reviewer up to 12 losers with their dollars, stakes, strikes and spot levels (never a ticker or a clock time), so every reply
is screened first: `python3 -m lossreview.screen NAME < reply.txt` (from a checkout, `PYTHONPATH=python`; it prints only the screened
JSON) keeps the step's own fields, drops prose, rounds a threshold to 3 significant figures, keeps eq values to short words and
strips digits, `$` and `%` from the mechanism and the note. The `responses` stage accepts only a reply that screening leaves
unchanged, so raw model text is refused; a reply screening empties (exit 1) is asked of the model once more with "no figures in the
text" and dropped if it still fails. The prompts and the trip files do hold per-trade values: they stay on Drive and in the runner's
temporary folder, and the job log prints only what `daily.py` prints (never a ticker, a time or a count of a window).

Stage inputs: `day` (UTC day), `stages` (in order, comma or space separated: `pending prepare-tags apply-tags prepare-hyp apply-hyp
apply-adv sweep shadow status budget window done`), `usage` (`step:tokens_in:tokens_out:items;...`, logged first), `responses`,
`weekly`, `since`/`until` (the window stage, 00:00 to 23:59:59 or 24:00). Every run pulls the trip files, `registry.jsonl`,
`usage.jsonl`, the done marks and the day's work folder, runs the canary (a broken validator stops it before it writes anything),
logs the usage, saves the responses, runs the stages, and puts back `registry.jsonl` and `usage.jsonl`, then `work/DAY/` (so a put
that stops half way never leaves a day done without its registry). A failed stage stops the run before the put.
Dispatch one run at a time and wait for it to finish (the workflow's concurrency group keeps a second one waiting, and a third
replaces the second). Never dispatch again a dispatch that succeeded: its replies are saved and its usage logged; read the job
log first when the outcome is unknown.

Finding a day's prompt files: names repeat in every day's folder, so resolve the folder first (Drive connector: the folder
`derived/loss-review/work`, then the folder named `D` in it, by `parentId`) and list that folder's files. `apply-hyp` prints
the ids it wrote adversary prompts for (`adv_ids`), `prepare-hyp` the classes it wrote hypothesis prompts for.

## Steps

1. Dispatch `day=<yesterday> stages=pending,status`. The `pending` line names the days still to do, oldest first, and `next` the
   step each stands at; none: stop and say so in one line. For each day `D`, continue from its `next` step (a day that is new
   starts at 2; one the allowance interrupted resumes where its files say), then the next day.
2. `prepare-tags`: dispatch `day=D stages=prepare-tags,budget`. If `budget` says `"ok": false`, stop (the day waits at `apply-tags`).
   `batches` 0 means nothing to review: go to the second dispatch of step 3 with no tag replies. Else, for each `work/D/tag-NN.prompt.txt`,
   a Haiku subagent reads it and returns the JSON; screen each reply.
3. `apply-tags`: dispatch `day=D stages=apply-tags,prepare-hyp,budget responses={tag-NN: screened...} usage=tag:IN:OUT:ITEMS`.
   `classes` empty: dispatch `apply-hyp` with no responses and go to step 5. Else, for each `work/D/hyp-CLASS.prompt.txt`, a Sonnet subagent;
   screen each reply.
4. `apply-hyp`: dispatch `day=D stages=apply-hyp,budget responses={hyp-CLASS: screened...} usage=hypothesize:IN:OUT:ITEMS`
   (`apply-hyp` validates every hypothesis: ex-ante columns only, closed lever set, at most 12 thresholds and 2 neighbors, at most 3 a
   class and 6 a day, unique ids, and no repeat of an idea already registered, refuted ones included; it writes the adversary
   prompts with the blind winner control). For each id in `adv_ids`, a Sonnet subagent reads `adv-ID.prompt.txt` (it sees the
   hypothesis and aggregates only, never a ticker); screen each reply.
5. `apply-adv`: dispatch `day=D stages=apply-adv,sweep,shadow,status,done responses={adv-ID: screened...} usage=adversary:IN:OUT:ITEMS`:
   `apply-adv` refuses to run while any admitted hypothesis has no adversary reply (a missing reply waits, it does not register the
   idea unreviewed), then registers survivors (every threshold and neighbor candidate counts as a trial); `sweep` reads every open
   hypothesis at its next fixed look, 4, 8 or 12 scoring days after its generating losses, never nightly, and freezes a candidate
   that survives BH over the registry, with the window's last day as `frozen_day`; `shadow` counts only days after `frozen_day`,
   flags D's trips with every frozen rule and looks at 5 and 10 shadow days (a rule that is ready moves to `proposal`, one that is
   not ready by day 10 fades to `retired`); `done` marks the day, and refuses while an admitted hypothesis is not registered.
6. Post at most one short message: counts only (reviewed losers, hypotheses admitted and refuted, candidates, shadow rules, rules
   ready for a PR, tokens used). No tickers, no per-trade values.
7. A rule that is `ready` is written up as a promotion PR in the style of the size dial (#346: off / log / on, a differential
   test that the heat curves' calls are identical with the rule on and off) and put to the owner; it is never merged by the
   routine. A curve edit (a rule on `rank`, `heat`, `weight`, `call_key`, ...) waits in `swept` until the owner says so.

A subagent token count that the tool does not report is estimated (prompt length / 4 in, reply length / 4 out) and logged as such;
keep the estimate on the high side, since an under-count only makes the allowance look larger than it is.

To check that a day agrees with an earlier hand study, dispatch `stages=window since=00:00 until=HH:MM:SS`: the window's full
summary goes to `work/D/window-*.json` on Drive (read it with the connector). The log shows neither a count nor a dollar figure:
the bounds are public inputs to the second, so two windows a few seconds apart would subtract down to a single trade.

## What the model steps must not do

- Free text is never a rule. Only a form that `forms.validate_hypothesis` accepts reaches the registry.
- Outcome columns are context, not features: the model sees them in a separate block and the validator refuses a hypothesis that
  names one.
- No claim of an effect: the sweep decides, from unseen days, against its placebo.
- The first dry night runs steps 2 to 5 once on the Nov 12 file and the result is read before the routine is scheduled.
