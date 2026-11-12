#!/usr/bin/env bash
# Status codes only. 000 = no answer (blocked or timed out); 451 = refused for the region.
get() { printf '%-46s ' "$1"; curl -sS -m 8 -o /dev/null -w '%{http_code} %{time_total}s\n' "$2" 2>&1 | tail -1; }
ws() { printf '%-46s ' "$1"; curl -sS -m 5 -i -N --http1.1 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
         -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$2" 2>&1 | head -1 | tr -d '\r' || true; echo; }
echo "host: $(date -u +%FT%TZ)"
get 'binance futures ping'            https://fapi.binance.com/fapi/v1/ping
get 'binance spot ping'               https://api.binance.com/api/v3/ping
get 'binance data-api.vision ping'    https://data-api.binance.vision/api/v3/ping
get 'coinalyze api (no key)'          https://api.coinalyze.net/v1/exchanges
get 'bybit time'                      https://api.bybit.com/v5/market/time
get 'okx time'                        https://www.okx.com/api/v5/public/time
get 'coinbase time'                   https://api.exchange.coinbase.com/time
ws  'ws fstream.binance.com aggTrade'  https://fstream.binance.com/ws/btcusdt@aggTrade
ws  'ws data-stream.binance.vision'    https://data-stream.binance.vision/ws/btcusdt@aggTrade
ws  'ws stream.bybit.com'              https://stream.bybit.com/v5/public/linear
