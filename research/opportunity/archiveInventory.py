"""Read-only, bounded metadata inventory of the bot's history store. No price rows or secrets are printed."""
import argparse
import csv
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import sys

TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
SAMPLE_BYTES = 16384


def stamp(text):
    """Normalize only numeric epochs or strict ISO timestamps; never echo unknown cells."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", text):
        try:
            result = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            result = result.replace(tzinfo=dt.timezone.utc) if result.tzinfo is None else result.astimezone(dt.timezone.utc)
            return result.isoformat().replace("+00:00", "Z") if 2000 <= result.year <= 2100 else None
        except ValueError:
            return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    value = float(text)
    if value > 1e14:
        value /= 1e6
    elif value > 1e11:
        value /= 1000
    try:
        result = dt.datetime.fromtimestamp(value, dt.timezone.utc)
        return result.isoformat().replace("+00:00", "Z") if 2000 <= result.year <= 2100 else None
    except (ValueError, OverflowError, OSError):
        return None


def summarize_csv_samples(head, tail=b"", tail_partial=False):
    """Infer spacing only within bounded samples; never across the unsampled middle."""
    lines = head.decode("utf-8", errors="replace").splitlines()
    if len(head) == SAMPLE_BYTES and not head.endswith(b"\n"):
        lines = lines[:-1]
    if not lines:
        return {"header": "unrecognized", "full_file_validation": False}
    fields = next(csv.reader([lines[0]]))
    names = [f.strip().lower().lstrip("\ufeff") for f in fields]
    times = [i for i, name in enumerate(names) if name in ("ts", "time", "timestamp", "open_time", "open time", "unix", "date", "datetime")]
    known = bool(times) and (set(("o", "h", "l", "c")).issubset(names) or set(("open", "high", "low", "close")).issubset(names))
    def values(rows):
        out = []
        for cells in csv.reader(rows):
            if len(cells) != len(names):
                continue
            text = cells[times[0]].strip()
            value = stamp(text)
            if value is not None:
                out.append(value)
        return out
    if not known:
        return {"header": "unrecognized", "full_file_validation": False}
    first = values(lines[1:])
    tail_lines = tail.decode("utf-8", errors="replace").splitlines()
    if tail_partial:
        tail_lines = tail_lines[1:]
    last = values(tail_lines) if tail and tail != head else []
    intervals = Counter()
    for segment in [first, last]:
        for a, b in zip(segment, segment[1:]):
            seconds = (dt.datetime.fromisoformat(b.replace("Z", "+00:00")) - dt.datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds()
            intervals[str(int(seconds)) if seconds.is_integer() else str(seconds)] += 1
    return {"header": "recognized", "first_open_utc": first[0] if first else None,
            "last_open_utc": (last[-1] if last else first[-1] if first and tail else None),
            "sampled_cadence_seconds": dict(intervals), "sampled_rows": len(first) + len(last),
            "has_60_second_steps": intervals.get("60", 0) > 0,
            "all_sampled_steps_60_seconds": bool(intervals) and set(intervals) == {"60"},
            "full_file_validation": False}


def inspect_csv(file, base, source, asset, tf):
    entry = {"path": file.relative_to(base).as_posix(), "source": source, "asset": asset,
             "tf": tf, "provenance_verified": False}
    try:
        if not file.resolve().is_relative_to(base.resolve()):
            return {**entry, "status": "symlink-outside-root"}
        before = file.stat()
        with file.open("rb") as stream:
            head = stream.read(SAMPLE_BYTES)
            stream.seek(max(0, before.st_size - SAMPLE_BYTES))
            tail = stream.read(SAMPLE_BYTES)
        after = file.stat()
        sample = summarize_csv_samples(head, tail, before.st_size > SAMPLE_BYTES)
        known = sample["header"] == "recognized"
        first, last = sample.get("first_open_utc"), sample.get("last_open_utc")
        tv_layout = source in ("tradingview", "tvspot", "tv-export") or source.startswith("tvdatafeed-")
        sidecar = file.with_name(file.name + ".provenance.json")
        declared = False
        if sidecar.is_file() and sidecar.resolve().is_relative_to(base.resolve()) and sidecar.stat().st_size <= 65536:
            try:
                proof = json.loads(sidecar.read_text())
                declared = proof.get("provider") == "tvdatafeed"
            except (OSError, ValueError, AttributeError):
                pass
        return {**entry, "size_bytes": before.st_size, "sampled_bytes": len(head) + len(tail),
                **sample,
                "tv_evidence": "sidecar-declaration" if declared else "repository-tv-layout" if tv_layout else "non-tv-layout",
                "status": "changed-during-read" if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                else "ok" if known and first and last else "unrecognized-csv"}
    except OSError as error:
        return {**entry, "status": type(error).__name__}


def inventory(root, incoming=None, max_files=5000):
    root = Path(root).expanduser()
    report = {"schema": "atlas-archive-inventory-v1", "read_only": True, "files": [],
              "root_exists": root.is_dir(), "truncated": False,
              "scope": "source and asset CSVs (one nested level), plus recognized raw exports; header/tail samples"}
    candidates = []
    if root.is_dir():
        for source in sorted(root.iterdir()):
            if not source.is_dir() or not source.resolve().is_relative_to(root.resolve()):
                continue
            for file in sorted(source.glob("*.csv")):
                candidates.append((file, root, source.name, "unknown", file.stem if file.stem in TIMEFRAMES else "unknown"))
            for asset in sorted(source.iterdir()):
                if not asset.is_dir() or not asset.resolve().is_relative_to(root.resolve()):
                    continue
                for file in sorted([*asset.glob("*.csv"), *asset.glob("*/*.csv")]):
                    tf = file.stem if file.stem in TIMEFRAMES else file.parent.name if file.parent.name in TIMEFRAMES else "unknown"
                    candidates.append((file, root, source.name, asset.name, tf))
    if incoming and Path(incoming).expanduser().is_dir():
        raw = Path(incoming).expanduser()
        for file in sorted(raw.glob("*.csv")):
            match = re.fullmatch(r"tvspot__([A-Z0-9]+)__(1m|5m|15m|1h|4h|1d)__[A-Z0-9_-]+\.csv", file.name)
            index = re.fullmatch(r"(?:CRYPTOCAP|TVINDEX)_([A-Z0-9.]+)_(1m|5m|15m|1h|4h|1d)\.csv", file.name)
            if match or index:
                asset, tf = (match or index).groups()
                candidates.append((file, raw, "tv-export", asset, tf))
    report["truncated"] = len(candidates) > max_files
    for args in candidates[:max_files]:
        report["files"].append(inspect_csv(*args))
    report["tv_minute_candidates"] = [f["path"] for f in report["files"]
                                      if f["tf"] == "1m" and f.get("tv_evidence") in
                                      ("repository-tv-layout", "sidecar-declaration") and f["status"] == "ok"]
    report["minute_spacing_observed"] = [f["path"] for f in report["files"] if f.get("has_60_second_steps") and f["status"] == "ok"]
    report["minute_samples_confirmed"] = [f["path"] for f in report["files"] if f.get("all_sampled_steps_60_seconds") and f["status"] == "ok"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="~/bot/data/history")
    parser.add_argument("--incoming", default="~/bot/data/incoming/tradingview")
    args = parser.parse_args()
    report = inventory(args.root, args.incoming)
    print(json.dumps(report, indent=2))
    return 0 if report["root_exists"] and not report["truncated"] else 1


if __name__ == "__main__":
    sys.exit(main())
