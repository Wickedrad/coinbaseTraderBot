"""List project Drive archive metadata through rclone. No downloads, uploads or secret output."""
import argparse
import json
import re
import subprocess
import sys
import time

CONTAINERS = {"raw", "history", "server-history", "data", "incoming", "tradingview", "tvspot", "tvdatafeed", "tv-history", "kalshi-bot-archive"}
HISTORY_SOURCES = {"binance", "binance-1m", "binance-um", "binance-index", "binance-oi",
                   "coinbase", "coinbase-1m", "bitstamp", "kraken", "gemini", "cdd", "bittrex", "other",
                   "yahoo", "yfinance", "yahoo-finance", "yahoo-history"}
YAHOO_SOURCES = {"yahoo", "yfinance", "yahoo-finance", "yahoo-history"}


def classify_error(text):
    for value in ("invalid_grant", "invalid_client", "directory not found", "permission denied"):
        if value in text.lower():
            return value
    match = re.search(r"\b(401|403|404|429|500|503)\b", text)
    return f"HTTP {match[1]}" if match else "rclone listing failed"


def listing(remote, recursive=False, folder_id=None):
    args = ["rclone", "lsjson", remote, "--max-depth", "4" if recursive else "1",
            "--contimeout", "15s", "--timeout", "30s", "--retries", "1", "--low-level-retries", "2"]
    if recursive:
        args += ["--recursive", "--files-only"]
    if folder_id:
        args += ["--drive-root-folder-id", folder_id]
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=45)
        if process.returncode:
            return None, classify_error(process.stderr)
        if len(process.stdout) > 16 * 1024 * 1024:
            return None, "listing exceeded 16 MiB"
        data = json.loads(process.stdout)
        if not isinstance(data, list):
            return None, "invalid listing JSON"
        return data, None
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return None, type(error).__name__


def inventory(folder_id=None, list_fn=listing):
    roots = [("configured-archive", "gdrive:kalshi-bot-archive", None)]
    if folder_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", folder_id):
            raise ValueError("invalid shared folder id")
        roots.append(("linked-folder", "gdrive:", folder_id))
    report = {"schema": "atlas-drive-inventory-v1", "read_only": True,
              "scope": "project archive containers and known market-history source namespaces; metadata only", "roots": []}
    deadline = time.monotonic() + 240
    for label, root, override in roots:
        result = {"label": label, "accessible": False, "files": [], "scanned_folders": [], "errors": [], "truncated": False}
        queue = [(root, "", 0)]
        visited = set()
        while queue and len(visited) < 30 and time.monotonic() < deadline:
            remote, relative, depth = queue.pop(0)
            if remote in visited:
                continue
            visited.add(remote)
            entries, error = list_fn(remote, False, override)
            if error:
                result["errors"].append({"path": relative or ".", "error": error})
                continue
            if not relative:
                result["accessible"] = True
            for entry in entries:
                name = entry.get("Name", "")
                if not isinstance(name, str) or name in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_. -]+", name):
                    continue
                child_rel = f"{relative}/{name}".lstrip("/")
                child = f"{remote.rstrip('/')}/{name}" if not remote.endswith(":") else remote + name
                canonical = name.lower().replace("_", "-").replace(" ", "-")
                tv = canonical in ("tradingview", "tvspot", "tvdatafeed", "tv-history") or canonical.startswith("tvdatafeed-")
                if entry.get("IsDir") and (tv or canonical in HISTORY_SOURCES):
                    files, error = list_fn(child, True, override)
                    if error:
                        result["errors"].append({"path": child_rel, "error": error})
                        continue
                    result["scanned_folders"].append(child_rel)
                    for file in files:
                        if file.get("IsDir") or not str(file.get("Name", "")).lower().endswith((".csv", ".zip", ".csv.gz")):
                            continue
                        file_path = str(file.get("Path", file.get("Name", "")))
                        minute = bool(re.search(r"(?:^|[/_-])1m(?:[/_.-]|$)", file_path))
                        result["files"].append({"path": f"{child_rel}/{file_path}", "size_bytes": file.get("Size"),
                                                "modified": file.get("ModTime"), "minute_named": minute,
                                                "source_namespace": name,
                                                "source_evidence": "tv-layout" if tv else "yahoo-layout" if canonical in YAHOO_SOURCES else "non-tv-layout",
                                                "provenance_verified": False})
                        if len(result["files"]) >= 5000:
                            result["truncated"] = True
                            break
                elif entry.get("IsDir") and canonical in CONTAINERS and depth < 4:
                    queue.append((child, child_rel, depth + 1))
            if result["truncated"]:
                break
        if queue:
            result["truncated"] = True
        result["tv_minute_candidates"] = [f["path"] for f in result["files"] if f["minute_named"] and f["source_evidence"] == "tv-layout"]
        result["other_minute_files"] = [f["path"] for f in result["files"] if f["minute_named"] and f["source_evidence"] != "tv-layout"]
        result["yahoo_layout_files"] = [f["path"] for f in result["files"] if f["source_evidence"] == "yahoo-layout"]
        report["roots"].append(result)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-id")
    args = parser.parse_args()
    report = inventory(args.folder_id)
    print(json.dumps(report, indent=2))
    return 0 if any(r["accessible"] for r in report["roots"]) else 1


if __name__ == "__main__":
    sys.exit(main())
