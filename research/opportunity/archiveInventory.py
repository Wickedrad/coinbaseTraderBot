"""Read-only, bounded metadata inventory of the bot's history store. No price rows or secrets are printed."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
HEADERS = {"ts,o,h,l,c,v", "ts,o,h,l,c,v,tb", "time,open,high,low,close,volume"}
SAMPLE_BYTES = 16384


def stamp(text):
    """Only canonical numeric epoch stamps; never echo an unrecognized cell."""
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
        lines = head.decode("utf-8", errors="replace").splitlines()
        header = lines[0].strip() if lines else ""
        known = header in HEADERS
        first = next((stamp(line.split(",", 1)[0]) for line in lines[1:]
                      if stamp(line.split(",", 1)[0]) is not None), None) if known else None
        last = next((stamp(line.split(",", 1)[0]) for line in reversed(tail.decode("utf-8", errors="replace").splitlines())
                     if stamp(line.split(",", 1)[0]) is not None), None) if known else None
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
                "header": "recognized" if known else "unrecognized", "first_open_utc": first, "last_open_utc": last,
                "tv_evidence": "sidecar-declaration" if declared else "repository-tv-layout" if tv_layout else "non-tv-layout",
                "status": "changed-during-read" if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                else "ok" if known and first and last else "unrecognized-csv"}
    except OSError as error:
        return {**entry, "status": type(error).__name__}


def inventory(root, incoming=None, max_files=5000):
    root = Path(root).expanduser()
    report = {"schema": "atlas-archive-inventory-v1", "read_only": True, "files": [],
              "root_exists": root.is_dir(), "truncated": False,
              "scope": "source/asset/timeframe.csv plus recognized raw TradingView exports; header/tail only"}
    candidates = []
    if root.is_dir():
        for source in sorted(root.iterdir()):
            if not source.is_dir() or not source.resolve().is_relative_to(root.resolve()):
                continue
            tv = source.name in ("tradingview", "tvspot") or source.name.startswith("tvdatafeed-")
            for asset in sorted(source.iterdir()):
                if not asset.is_dir() or not asset.resolve().is_relative_to(root.resolve()):
                    continue
                for file in sorted(asset.glob("*.csv")):
                    if file.stem in TIMEFRAMES and (tv or file.stem == "1m"):
                        candidates.append((file, root, source.name, asset.name, file.stem))
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
