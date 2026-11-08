"""Stream-audit archived OHLCV files without cleaning, fitting or modifying them."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sys

ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]


def audit_file(file, root, interval_ms):
    result = {"path": file.relative_to(root).as_posix(), "source": file.relative_to(root).parts[0],
              "interval_ms": interval_ms, "rows": 0, "invalid_rows": 0, "duplicate_or_reversed": 0,
              "misaligned": 0, "gap_events": 0, "missing_bars": 0, "invalid_taker_volume": 0,
              "first_open_ms": None, "last_open_ms": None, "ready": False,
              "provider_identity": "archive-path-declaration; not independently authenticated"}
    before = file.stat()
    digest = hashlib.sha256()
    # Hash exact transport bytes separately so newline normalization cannot hide changes.
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    last = None
    with file.open(newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        if header not in (["ts", "o", "h", "l", "c", "v"], ["ts", "o", "h", "l", "c", "v", "tb"]):
            result["error"] = "unrecognized canonical OHLCV header"
        else:
            for row in reader:
                if not row:
                    continue
                result["rows"] += 1
                try:
                    if len(row) != len(header) or any(not x.strip() for x in row[:6]):
                        raise ValueError()
                    ts, o, h, l, c, v = map(float, row[:6])
                    if not all(map(math.isfinite, (ts, o, h, l, c, v))) or ts < 0 or ts != int(ts) or min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c) or v < 0:
                        raise ValueError()
                except (ValueError, OverflowError):
                    result["invalid_rows"] += 1
                    continue
                if len(row) == 7 and row[6].strip():
                    try:
                        tb = float(row[6])
                        if not math.isfinite(tb) or tb < 0 or tb > v + 1e-9:
                            raise ValueError()
                    except ValueError:
                        result["invalid_taker_volume"] += 1
                ts = int(ts)
                if ts % interval_ms:
                    result["misaligned"] += 1
                if last is not None:
                    if ts <= last:
                        result["duplicate_or_reversed"] += 1
                    elif ts > last + interval_ms:
                        result["gap_events"] += 1
                        result["missing_bars"] += max(0, (ts - last) // interval_ms - 1)
                result["first_open_ms"] = ts if result["first_open_ms"] is None else result["first_open_ms"]
                result["last_open_ms"] = ts
                last = ts
    after = file.stat()
    result["changed_during_audit"] = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    result["sha256"] = digest.hexdigest()
    result["bytes"] = before.st_size
    result["ready"] = result["rows"] > 0 and not any(result[k] for k in ("invalid_rows", "duplicate_or_reversed", "misaligned", "invalid_taker_volume", "changed_during_audit")) and "error" not in result
    result["continuous"] = result["ready"] and result["gap_events"] == 0
    return result


def audit_archive(root):
    root = Path(root).resolve()
    required = [f"binance-1m/{a}/1m.csv" for a in ASSETS]
    context = [f"yahoo/{a}/1d.csv" for a in ASSETS] + [f"tradingview/{a}/1d.csv" for a in ("BTC.D", "USDT.D")]
    report = {"schema": "atlas-archive-audit-v1", "research_only": True, "auto_promote": False,
              "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "files": [], "missing": []}
    for name in required + context:
        file = root / name
        if not file.is_file() or not file.resolve().is_relative_to(root):
            report["missing"].append(name)
            continue
        report["files"].append(audit_file(file, root, 60000 if name.endswith("1m.csv") else 86400000))
    by_path = {f["path"]: f for f in report["files"]}
    report["ready"] = all(name in by_path and by_path[name]["ready"] for name in required)
    report["context_ready"] = all(name in by_path and by_path[name]["ready"] for name in context)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = audit_archive(args.history)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print("Audited files:", len(report["files"]), "minute data ready:", report["ready"], "context ready:", report["context_ready"])
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
