"""Ralph queue state machine. Local file operations only; no workflow, bot, or API access.

The authoritative copy is on the ralph-state branch, never the public code branch.
This tool does not grade hypotheses or authorize promotion; only signed external
evaluator receipts may support a separate human-reviewed pass decision.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time
from contextlib import contextmanager

STATES = frozenset({
    "queued", "maker_running", "awaiting_ci", "diff_critique",
    "awaiting_merge", "awaiting_grader", "result_critique",
    "awaiting_look", "conditional", "passed", "iterate",
    "parked", "underpowered", "blocked_on_owner",
})
TRANSITIONS = {
    "queued": {"maker_running", "blocked_on_owner", "underpowered"},
    "maker_running": {"awaiting_ci", "iterate", "blocked_on_owner"},
    "awaiting_ci": {"diff_critique", "iterate", "blocked_on_owner"},
    "diff_critique": {"awaiting_merge", "iterate", "blocked_on_owner"},
    "iterate": {"maker_running", "parked", "blocked_on_owner"},
    "awaiting_merge": {"awaiting_grader", "blocked_on_owner"},
    "awaiting_grader": {"result_critique", "awaiting_look", "blocked_on_owner"},
    "result_critique": {"awaiting_look", "iterate", "blocked_on_owner"},
    "awaiting_look": {"conditional", "underpowered", "parked", "blocked_on_owner"},
    "conditional": {"awaiting_look", "blocked_on_owner"},
    "blocked_on_owner": {"queued"},
    "underpowered": {"queued"},
    "parked": set(),
    "passed": set(),
}
# No model or operator CLI may mark a job passed. The protected evaluator owns that verdict.
CRITIC_MINIMUM = {0: 1, 1: 2, 2: 3, 3: 5}
MAKER_PREFIXES = ("python/ralph/", "docs/ralph/")
PROTECTED_PREFIXES = ("python/ralph_eval/", "ralph/pins.json")
EXECUTABLE_STATES = frozenset({"maker_running"})
STOP_FILE = "STOP"
LEDGER_VERSION = 1

class GuardError(RuntimeError):
    """Refuse unsafe or ambiguous state mutations."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def is_maker_path(path: str) -> bool:
    norm = pathlib.PurePosixPath(path)
    if (not path or path.startswith("/") or "\\" in path or
            ".." in norm.parts or path != norm.as_posix()):
        return False
    return any(path.startswith(p) for p in MAKER_PREFIXES)


def classify_paths(paths: list[str], initial: int = 0) -> int:
    """Changed paths can only raise risk, never lower a registered class.

    R1 includes queue infrastructure and executable dataset/analysis harnesses.
    An R0 analysis-only job stays R0 only if none of these shared files changes.
    """
    risk = initial
    if risk not in CRITIC_MINIMUM:
        raise GuardError("invalid initial risk")
    infra = ("python/ralph/control.py", "python/ralph/window_core.py",
             "python/ralph/j06_window.py", "python/ralph/j06_rollup.py")
    for p in paths:
        if not is_maker_path(p):
            raise GuardError("maker may edit only python/ralph/** and docs/ralph/**")
        if p in infra or p.startswith("python/ralph/tests/"):
            risk = max(risk, 1)
    return risk


def require_critics(risk: int, verdicts: list[dict], owner_ok: bool = False,
                    stronger_review: bool = False) -> None:
    if risk not in CRITIC_MINIMUM:
        raise GuardError("unrecognized risk class")
    if risk == 3 and not owner_ok:
        raise GuardError("R3 requires explicit owner authorization")
    if risk >= 2 and not stronger_review:
        raise GuardError("R2/R3 require stronger-model gate review")
    allowed = {"correctness", "fees", "statistics", "safety", "mechanism"}
    angles = [v.get("angle") for v in verdicts]
    if len(angles) != len(set(angles)) or any(x not in allowed for x in angles):
        raise GuardError("critic angles must be distinct and approved")
    if len(angles) < CRITIC_MINIMUM[risk]:
        raise GuardError("not enough independent critic angles")
    for v in verdicts:
        if v.get("severity") in ("blocker", "major"):
            raise GuardError("unresolved blocker/major criticism")
    if any(v.get("severity") not in ("none", "minor", "nit") for v in verdicts):
        raise GuardError("unknown severity")


def fresh_ledger(jobs: list[dict]) -> dict:
    ids = [j.get("id") for j in jobs]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"(?:J\d{2}[a-z]?|S\d[a-z]?)", str(x)) for x in ids):
        raise GuardError("duplicate or invalid job ID")
    out = {}
    for j in jobs:
        risk = j.get("risk")
        if risk not in CRITIC_MINIMUM:
            raise GuardError("invalid job risk")
        out[j["id"]] = {"id": j["id"], "risk": risk, "state": "queued", "rounds": 0,
                        "trials": 0, "owner_ok": False, "critic_verdicts": [],
                        "receipts": [], "history": [], "needs_owner": j.get("needs_owner", False)}
    return {"schema": "ralph-ledger-1", "version": LEDGER_VERSION,
            "created_utc": utc_now(), "jobs": out, "order": ids,
            "halted": False, "consecutive_nulls": 0,
            "token": {"used_stage0": 0, "used_stage1": 0, "stage0_cap": 5_000_000,
                      "stage1_cap": 8_000_000, "weekly_cap": None, "used_week": 0},
            "lease": None, "events": []}


def check_ledger(d: dict) -> None:
    if d.get("schema") != "ralph-ledger-1" or d.get("version") != 1:
        raise GuardError("unrecognized ledger schema")
    if set(d["order"]) != set(d["jobs"]) or len(d["order"]) != len(d["jobs"]):
        raise GuardError("ledger order/job mismatch")
    for job in d["jobs"].values():
        if job["state"] not in STATES or job["risk"] not in CRITIC_MINIMUM:
            raise GuardError("invalid job state/risk")


def atomic_write(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with open(temp, "x", encoding="utf8") as fh:
            json.dump(data, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def exclusive(path: pathlib.Path):
    """One local writer. Remote runners must also use GitHub concurrency and CAS."""
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise GuardError("lease busy: another writer has the state file") from exc
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()} at={utc_now()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def load(path: pathlib.Path) -> dict:
    with path.open(encoding="utf8") as f:
        d = json.load(f)
    check_ledger(d)
    return d


def halt_check(state_file: pathlib.Path, ledger: dict) -> None:
    if ledger["halted"] or (state_file.parent / STOP_FILE).exists():
        raise GuardError("Ralph STOP is active")
    if ledger["consecutive_nulls"] >= 3:
        raise GuardError("three consecutive null jobs: stop loop and escalate")


def next_unpassed(d: dict) -> dict | None:
    """Only queued work is eligible; all other states require resolution."""
    for id_ in d["order"]:
        j = d["jobs"][id_]
        if j["state"] == "queued":
            return j
    return None


def transition(d: dict, id_: str, new: str, *, reason: str,
               expected: str | None = None) -> None:
    if id_ not in d["jobs"]:
        raise GuardError("unknown job")
    if new not in STATES:
        raise GuardError("unknown state")
    j = d["jobs"][id_]
    old = j["state"]
    if expected and old != expected:
        raise GuardError("stale state (compare-and-swap)")
    if new == "passed":
        raise GuardError("pass requires protected evaluator; not a maker operation")
    if new == "parked" and old != "iterate":
        raise GuardError("parking requires documented loser audit from iterate state")
    if new not in TRANSITIONS.get(old, set()):
        raise GuardError(f"invalid transition {old}->{new}")
    if not reason or len(reason.strip()) < 8:
        raise GuardError("transition requires meaningful reason")
    if new == "maker_running":
        other_active = [k for k, v in d["jobs"].items()
                        if k != id_ and v["state"] in EXECUTABLE_STATES]
        if other_active:
            raise GuardError("single-worker rule: another maker is running")
        if j["rounds"] >= 3:
            raise GuardError("maker maximum three rounds reached")
        j["rounds"] += 1
    j["state"] = new
    event = {"at": utc_now(), "job": id_, "from": old, "to": new,
             "reason": reason[:400]}
    j["history"].append(event)
    d["events"].append(event)


def add_trials(d: dict, id_: str, count: int, why: str) -> None:
    if id_ not in d["jobs"] or not 0 < count <= 100_000 or not why.strip():
        raise GuardError("invalid trial update")
    d["jobs"][id_]["trials"] += count
    d["events"].append({"at": utc_now(), "job": id_, "trial_delta": count,
                        "why": why[:300]})


def record_usage(d: dict, stage: int, n: int) -> None:
    if stage not in (0, 1) or n < 0:
        raise GuardError("bad token count")
    t = d["token"]
    key, cap = (("used_stage0", "stage0_cap") if stage == 0 else
                ("used_stage1", "stage1_cap"))
    if t[key] + n > t[cap]:
        raise GuardError("stage token cap exceeded")
    if t["weekly_cap"] is None and n:
        raise GuardError("weekly token cap not pinned; do not dispatch model work")
    if t["weekly_cap"] is not None and t["used_week"] + n > t["weekly_cap"]:
        raise GuardError("weekly token cap exceeded")
    t[key] += n
    t["used_week"] += n


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ralph local guard + ledger (no network actions)")
    p.add_argument("--ledger", type=pathlib.Path, required=True)
    sp = p.add_subparsers(dest="command", required=True)
    sp.add_parser("status")
    sp.add_parser("next")
    move = sp.add_parser("move")
    move.add_argument("job")
    move.add_argument("state")
    move.add_argument("--expected", required=True)
    move.add_argument("--reason", required=True)
    count = sp.add_parser("count-trials")
    count.add_argument("job")
    count.add_argument("number", type=int)
    count.add_argument("--why", required=True)
    args = p.parse_args(argv)
    if args.command in ("status", "next"):
        d = load(args.ledger)
        result = {"halted": d["halted"], "stopped": (args.ledger.parent / STOP_FILE).exists(),
                  "null_streak": d["consecutive_nulls"], "next": next_unpassed(d)["id"] if next_unpassed(d) else None}
        if args.command == "status":
            result["jobs"] = {k: v["state"] for k, v in d["jobs"].items()}
        print(json.dumps(result))
        return 0
    with exclusive(args.ledger):
        d = load(args.ledger)
        halt_check(args.ledger, d)
        if args.command == "move":
            transition(d, args.job, args.state, reason=args.reason, expected=args.expected)
        else:
            add_trials(d, args.job, args.number, args.why)
        atomic_write(args.ledger, d)
    print(json.dumps({"ok": True, "job": args.job, "command": args.command}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(cli())
    except (GuardError, OSError, ValueError, KeyError) as exc:
        print(f"Ralph guard: {exc}", file=sys.stderr)
        sys.exit(2)
