"""Protected path-check logic for a required GitHub branch check.

This checker is not an ownership proof. The workflow MUST run base-branch-pinned
code and obtain an authenticated required-status check, never evaluate a script
from an untrusted pull-request branch with write permissions.
"""
from pathlib import PurePosixPath

MAKER_PREFIXES = ('python/ralph/', 'docs/ralph/')
EVALUATOR_PREFIXES = ('python/ralph_eval/', 'ralph/pins.json')
WORKFLOW_PREFIX = '.github/workflows/'


class PathViolation(ValueError):
    pass


def valid_path(path: str) -> bool:
    if not isinstance(path, str) or not path or '\\' in path or path.startswith('/'):
        return False
    p = PurePosixPath(path)
    return p.as_posix() == path and '..' not in p.parts and '.' not in p.parts


def maker_paths(paths: list[str]) -> dict:
    """Only maker-owned files allowed; no exception for an owner label in a maker PR."""
    if not paths:
        raise PathViolation('no changed paths')
    bad = [p for p in paths if not valid_path(p) or
           not any(p.startswith(root) for root in MAKER_PREFIXES)]
    if bad:
        # Never echo private absolute paths into public logs.
        raise PathViolation(f'{len(bad)} changed files outside maker allowlist')
    return {'status': 'allowed', 'count': len(paths), 'mode': 'maker'}


def protected_paths(paths: list[str], *, owner_approved: bool,
                    all_five_critics_clear: bool, strong_review_clear: bool) -> dict:
    """Protected scope is a *proposal*; caller must externally verify approval identity."""
    if not paths or not (owner_approved and all_five_critics_clear and strong_review_clear):
        raise PathViolation('protected edits require verified owner + five critics + strong gate review')
    bad = [p for p in paths if not valid_path(p) or
           not (any(p.startswith(root) for root in EVALUATOR_PREFIXES) or
                p.startswith(WORKFLOW_PREFIX))]
    if bad:
        raise PathViolation(f'{len(bad)} changed files outside protected allowlist')
    return {'status': 'scope_admissible', 'count': len(paths), 'mode': 'protected',
            'warning': 'approval identity must be verified by GitHub required check'}