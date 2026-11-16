import unittest

from ralph_eval.path_guard import PathViolation, maker_paths, protected_paths


class PathGuardTests(unittest.TestCase):
    def test_maker_cannot_touch_evaluator_or_workflows(self):
        self.assertEqual(maker_paths(['python/ralph/j22_scoreboard.py',
                                      'docs/ralph/ledger.md'])['status'], 'allowed')
        for path in ('bot/config.ts', '.github/workflows/test.yml', 'ralph/pins.json',
                     'python/ralph_eval/gates.py', 'python/ralph/../ralph_eval/gates.py',
                     '/root/secret', 'python\\ralph\\unsafe.py'):
            with self.subTest(path=path), self.assertRaises(PathViolation):
                maker_paths([path])

    def test_protected_requires_all_external_approvals(self):
        p = ['python/ralph_eval/gates.py', 'ralph/pins.json',
             '.github/workflows/ralph-path-guard.yml']
        with self.assertRaises(PathViolation):
            protected_paths(p, owner_approved=False, all_five_critics_clear=True,
                            strong_review_clear=True)
        self.assertEqual(protected_paths(p, owner_approved=True,
                                         all_five_critics_clear=True,
                                         strong_review_clear=True)['status'], 'scope_admissible')
        with self.assertRaises(PathViolation):
            protected_paths(['bot/engine.ts'], owner_approved=True,
                            all_five_critics_clear=True, strong_review_clear=True)