# OR-XD step P: server reachability probe

- Steven, Nov 12 2026 14:02 UTC (9:02 AM EST), in the thread "Build Binance history for heat curves": "yes Ok to run it" (the read-only reachability check from the Lightsail server).
- What runs: python/oracle/xd_probe.sh on the server over SSH (script on stdin, nothing written there, nice 19): one status-code call per public endpoint (Binance spot and futures APIs, data-api.binance.vision, Coinalyze without a key, Bybit, OKX, Coinbase) and three WebSocket handshakes. Prints status codes only; keeps no data; does not touch the bot process.
- Tag: [xd-probe-server] (job probe-server in .github/workflows/outside-xd.yml).
