import copy
import json
import tempfile
import unittest
from pathlib import Path

from ralph.control import (GuardError, add_trials, atomic_write, check_ledger,
                           classify_paths, exclusive, fresh_ledger, halt_check,
                           load, next_unpassed, record_usage, require_critics,
                           transition)


class RalphControlTests(unittest.TestCase):
    def test_first_jobs_are_direction(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}, {"id": "J06", "risk": 0}])
        self.assertEqual(next_unpassed(d)["id"], "J22")
        transition(d, "J22", "maker_running", expected="queued",
                   reason="analysis-only attempt")
        self.assertEqual(next_unpassed(d)["id"], "J06")
        self.assertEqual(d["jobs"]["J22"]["rounds"], 1)

    def test_pass_cannot_be_claimed_by_maker(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}])
        with self.assertRaises(GuardError):
            transition(d, "J22", "passed", reason="model claims an edge")
        self.assertEqual(d["jobs"]["J22"]["state"], "queued")

    def test_protected_paths_and_traversal_are_rejected(self):
        for p in ("bot/config.ts", "python/ralph_eval/gates.py", "ralph/pins.json",
                  "python/ralph/../ralph_eval/gates.py",
                  "/python/ralph/file.py", "python\\ralph\\file.py"):
            with self.subTest(p=p), self.assertRaises(GuardError):
                classify_paths([p], 0)
        self.assertEqual(classify_paths(["python/ralph/analysis.py", "docs/ralph/card.md"], 2), 2)

    def test_r3_requires_owner_and_five_critic_angles(self):
        verdicts = [{"angle": x, "severity": "none"}
                    for x in ("correctness", "fees", "statistics", "safety", "mechanism")]
        with self.assertRaises(GuardError):
            require_critics(3, verdicts, owner_ok=False, stronger_review=True)
        with self.assertRaises(GuardError):
            require_critics(3, verdicts, owner_ok=True, stronger_review=False)
        require_critics(3, verdicts, owner_ok=True, stronger_review=True)
        with self.assertRaises(GuardError):
            require_critics(3, verdicts[:-1], owner_ok=True, stronger_review=True)
        verdicts[0]["severity"] = "major"
        with self.assertRaises(GuardError):
            require_critics(3, verdicts, owner_ok=True, stronger_review=True)

    def test_no_more_than_three_maker_rounds(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}])
        j = d["jobs"]["J22"]
        for i in range(3):
            j["state"] = "iterate" if i else "queued"
            transition(d, "J22", "maker_running", reason="rerun after review")
        j["state"] = "iterate"
        with self.assertRaises(GuardError):
            transition(d, "J22", "maker_running", reason="fourth iteration forbidden")
        self.assertEqual(j["rounds"], 3)

    def test_trials_are_monotonic_and_counted(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}])
        add_trials(d, "J22", 4, "four frozen configurations")
        self.assertEqual(d["jobs"]["J22"]["trials"], 4)
        with self.assertRaises(GuardError):
            add_trials(d, "J22", -1, "undo the losers")

    def test_stop_and_null_streak_fail_closed(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            halt_check(path, d)
            (Path(tmp) / "STOP").touch()
            with self.assertRaises(GuardError):
                halt_check(path, d)
            (Path(tmp) / "STOP").unlink()
            d["consecutive_nulls"] = 3
            with self.assertRaises(GuardError):
                halt_check(path, d)

    def test_token_caps_cannot_overrun_or_run_unpinned(self):
        d = fresh_ledger([{"id": "J22", "risk": 0}])
        with self.assertRaises(GuardError):
            record_usage(d, 0, 100)
        d["token"]["weekly_cap"] = 1_000
        record_usage(d, 0, 800)
        with self.assertRaises(GuardError):
            record_usage(d, 0, 201)
        self.assertEqual(d["token"]["used_stage0"], 800)

    def test_atomic_ledger_and_local_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            d = fresh_ledger([{"id": "J22", "risk": 0}])
            atomic_write(path, d)
            with exclusive(path):
                with self.assertRaises(GuardError):
                    with exclusive(path):
                        pass
            self.assertEqual(load(path)["schema"], "ralph-ledger-1")
            (path.parent / "STOP").touch()
            with self.assertRaises(GuardError):
                halt_check(path, load(path))


if __name__ == "__main__":
    unittest.main()
