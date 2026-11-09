"""Stream-audit archived OHLCV files without cleaning, fitting or modifying them."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
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


def audit_archive(root, source="binance-1m", assets=None):
    root = Path(root).resolve()
    assets = ASSETS if assets is None else list(assets)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", source):
        raise ValueError("invalid archive source")
    if not assets or len(set(assets)) != len(assets) or any(a not in ASSETS for a in assets):
        raise ValueError("invalid archive assets")
    required = [f"{source}/{a}/1m.csv" for a in assets]
    context = [f"yahoo/{a}/1d.csv" for a in ASSETS] + [f"tradingview/{a}/1d.csv" for a in ("BTC.D", "USDT.D")]
    report = {"schema": "atlas-archive-audit-v1", "research_only": True, "auto_promote": False,
              "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "required_source": source,
              "required_assets": assets, "files": [], "missing": []}
    for name in required + context:
        file = root / name
        if not file.is_file() or not file.resolve().is_relative_to(root):
            report["missing"].append(name)
            continue
        report["files"].append(audit_file(file, root, 60000 if name.endswith("1m.csv") else 86400000))
    by_path = {f["path"]: f for f in report["files"]}
    report["ready"] = all(name in by_path and by_path[name]["ready"] for name in required)
    report["context_ready"] = all(name in by_path and by_path[name]["ready"] for name in context)
    for asset in ASSETS:
        funding = root / 'binance-funding' / asset / 'funding.csv'
        if funding.is_file() and funding.resolve().is_relative_to(root):
            report['files'].append(audit_funding(funding, root))
    return report


def audit_funding(file, root):
    result = {'path': file.relative_to(root).as_posix(), 'source': 'binance-funding', 'rows': 0,
              'invalid_rows': 0, 'duplicate_or_reversed': 0, 'first_open_ms': None, 'last_open_ms': None,
              'provider_identity': 'archive-path-declaration; not independently authenticated', 'ready': False}
    before = file.stat(); last = None; h = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    with file.open(newline='') as stream:
        reader = csv.reader(stream)
        if next(reader, []) != ['ts', 'rate']:
            result['error'] = 'unrecognized funding header'
        else:
            for row in reader:
                if not row:
                    continue
                result['rows'] += 1
                try:
                    if len(row) != 2 or any(not s.strip() for s in row): raise ValueError()
                    ts, rate = map(float, row)
                    if not math.isfinite(ts) or ts < 0 or ts != int(ts) or not math.isfinite(rate): raise ValueError()
                    ts = int(ts)
                except (ValueError, OverflowError):
                    result['invalid_rows'] += 1; continue
                if last is not None and ts <= last: result['duplicate_or_reversed'] += 1
                if result['first_open_ms'] is None: result['first_open_ms'] = ts
                result['last_open_ms'] = last = ts
    after = file.stat(); result.update(sha256=h.hexdigest(), bytes=before.st_size,
        changed_during_audit=(before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns))
    result['ready'] = result['rows'] > 0 and not any(result[k] for k in ('invalid_rows', 'duplicate_or_reversed', 'changed_during_audit')) and 'error' not in result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history")
    parser.add_argument("--source", default="binance-1m")
    parser.add_argument("--assets", default=",".join(ASSETS))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = audit_archive(args.history, args.source, args.assets.split(","))
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print("Audited files:", len(report["files"]), "minute data ready:", report["ready"], "context ready:", report["context_ready"])
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
