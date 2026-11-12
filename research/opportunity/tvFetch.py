"""Atlas-only tvdatafeed bridge. No venue fallback, credentials, or alternate providers."""
import contextlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
if os.environ.get("SSL_CERT_FILE"):
    os.environ.setdefault("WEBSOCKET_CLIENT_CA_BUNDLE", os.environ["SSL_CERT_FILE"])

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deploy.tv_history import epoch_seconds, fetch as fetch_history


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def main():
    from tvDatafeed import Interval, TvDatafeed
    plan = json.load(sys.stdin)
    bars = plan["bars"]
    if not isinstance(bars, int) or not 1 <= bars <= 5000 or not 1 <= len(plan["series"]) <= 22:
        raise ValueError("invalid bounded tvdatafeed plan")
    intervals = {"1m": Interval.in_1_minute, "1d": Interval.in_daily}
    distribution = importlib.metadata.distribution("tvdatafeed")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    # Only public source identity, never URL credentials or queries.
    parts = urlsplit(direct.get("url", ""))
    source = f"{parts.scheme}://{parts.hostname}{parts.path}" if parts.hostname else None
    result = {"schema": "atlas-tvdatafeed-v1", "provider": "tvdatafeed",
              "clientVersion": distribution.version, "clientSource": source, "series": []}
    with contextlib.redirect_stdout(sys.stderr):
        tv = TvDatafeed()  # Deliberately no login or credential arguments.
        for request in plan["series"]:
            item = {"id": request["id"], "rows": [], "error": None}
            try:
                df = fetch_history(tv, request["exchange"], request["symbol"],
                                   intervals[request["tf"]], bars, tries=2)
                if df is None or df.empty:
                    raise ValueError("tvdatafeed returned no bars")
                expected = f"{request['exchange']}:{request['symbol']}"
                if "symbol" not in df or set(df["symbol"]) != {expected}:
                    raise ValueError("returned symbol does not match the requested venue and symbol")
                for stamp, row in df.iterrows():
                    item["rows"].append([epoch_seconds(stamp) * 1000,
                                         *[finite(row.get(key)) for key in ("open", "high", "low", "close", "volume")]])
            except Exception as error:
                item["rows"] = []
                item["error"] = f"{type(error).__name__}: {error}"[:500]
            finally:
                ws = getattr(tv, "ws", None)
                if ws is not None:
                    ws.close()
            result["series"].append(item)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
