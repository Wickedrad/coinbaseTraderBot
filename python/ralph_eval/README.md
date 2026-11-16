# Protected deterministic Ralph evaluator — draft, NOT pinned

This code must never be edited by a Ralph maker. Its repository path is deliberately separate from python/ralph/** and docs/ralph/**. Changing the grader, gates, fee implementation, owner approval policy or pins requires explicit owner authorization, all five independent critic angles, a stronger-model review, and a required GitHub guard check.

Policy draft in ralph/pins.json has status DRAFT_UNPINNED and can_grade_binding=false. The source hash is recorded but not independently approved. These functions produce diagnostic or conditional verdicts only; they never mark jobs passed, modify the queue, run a bot, trade or deploy.

The owner-requested numerical defaults are fixed in source: direction beats same-contract/hour random side by 2x clustered SE; 9 positive days in 12; 12-day execution look with 1-day embargo, harm checks at days 4 and 8, one-sided alpha 0.10, BH q 0.10, >=85% of decision baseline, placebo below half gap, and $200 no-refill Stage 1 paper pool. MDE uses a t-quantile plus 80% power normal quantile (about $64/day for paired, $128/day for 6-vs-6 at $100/day assumed SD).

The precise definition of coin/side 'clearly negative' is still unresolved: direction_gate refuses a binding result without a pinned definition and a signed, separately supplied slot-clustered score. This code's 12-day daily score is a diagnostic and cannot substitute for the first-signal duration test or executable Kalshi book evidence. Alternative-day arms are scored as two independent sets of days, not as fictitious same-day pairs.

The companion path_guard.py enforces the maker allowlist and checks whether protected changes are limited to protected paths. The latter's Boolean inputs ARE NOT proof of owner approval. A future required GitHub check must read approval from trusted GitHub metadata and use trusted base-branch code; never run untrusted PR code with write credentials.

Run focused local verification:

    PYTHONPATH=python python3 -m unittest discover -s python/ralph_eval/tests -v

No evaluator file may merge into main until the owner-approved pin, review, and required GitHub path guard exist. Nothing here changes bot runtime behavior.
