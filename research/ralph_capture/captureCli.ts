/** Read-only raw frame capture from Kalshi's WebSocket. RESEARCH ONLY: never run by the bot, never run by CI.
 *
 *  It connects with the existing KalshiWs client, subscribes the market data channels for the tickers you give, and writes
 *  the hash-chained journal of research/ralph_capture/rawTap.ts. It calls no REST endpoint and sends no order. Because
 *  KalshiWs subscribes the account's `fill` and `user_orders` channels whenever it is given a signer, those frames still
 *  arrive; the tap withholds their content (length and SHA-256 only).
 *
 *  Needs the owner's authorization and a Kalshi key. It refuses to start without --authorized-by-owner, reads the key from
 *  KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH (same names as the bot), and never writes either anywhere.
 *
 *    npx tsx research/ralph_capture/captureCli.ts --authorized-by-owner --out /path/to/private-dir \
 *      --tickers KXBTC15M-26NOV18...,KXETH15M-... [--seconds 3600] [--ws-url wss://...] [--mode paper]
 *
 *  Afterwards: python3 research/ralph_capture/verify_journal.py DIR/<file>.journal --anchor DIR/<file>.anchor
 *  and copy the .anchor file (or just its last line) somewhere this machine cannot edit it. */
import fs from 'node:fs';
import path from 'node:path';
import { KalshiSigner } from '../../bot/kalshi/auth';
import { KalshiWs } from '../../bot/kalshi/ws';
import { RawFrameTap } from './rawTap';

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

async function main(): Promise<void> {
  if (!process.argv.includes('--authorized-by-owner')) throw new Error('refusing to connect without --authorized-by-owner');
  const out = arg('out');
  const tickers = (arg('tickers') ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  if (!out || !tickers.length) throw new Error('--out DIR and --tickers A,B are required');
  const keyId = process.env.KALSHI_KEY_ID, keyPath = process.env.KALSHI_PRIVATE_KEY_PATH;
  if (!keyId || !keyPath) throw new Error('KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set');
  const url = arg('ws-url') ?? process.env.KALSHI_WS_URL ?? 'wss://api.elections.kalshi.com/trade-api/ws/v2';
  const seconds = Number(arg('seconds') ?? 600);
  if (!Number.isFinite(seconds) || seconds <= 0) throw new Error('--seconds must be positive');
  const signer = KalshiSigner.fromFile(keyId, keyPath);   // before any file exists: a bad key path leaves nothing behind
  fs.mkdirSync(out, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(out, `kalshi-ws-${stamp}.journal`);
  const u = new URL(url);
  const tap = new RawFrameTap({
    file, anchorFile: path.join(out, `kalshi-ws-${stamp}.anchor`), anchorEvery: 500,
    onAnchor: (a) => console.log(JSON.stringify({ anchor: a })),
    // Frozen before the first frame: what was asked for, where, and by what tool. No credentials, no headers.
    config: { tool: 'ralph_capture/captureCli', schema: 1, ws_host: u.host, ws_path: u.pathname, tickers, seconds, mode: arg('mode') ?? 'paper', channels_requested: ['orderbook_delta', 'trade', 'market_lifecycle_v2'], private_channels_redacted: true },
  });
  const ws = new KalshiWs(url, signer, []);
  ws.setRawSink(tap);
  ws.setMarkets(tickers);
  ws.connect();
  // Ctrl-C or the timer ends the capture the same way: close the socket, write the footer, then exit (KalshiWs can be
  // revived by a pending reconnect timer, so the process is ended explicitly rather than left to drain).
  await new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, seconds * 1000);
    for (const sig of ['SIGINT', 'SIGTERM'] as const) process.once(sig, () => { clearTimeout(timer); resolve(); });
  });
  ws.close();
  await new Promise<void>((r) => setTimeout(r, 500));
  await tap.close();
  console.log(JSON.stringify({ file, status: tap.status(), exchange_authenticated: false }));
  process.exit(tap.status().failed ? 2 : 0);
}

main().catch((e) => { console.error(String(e instanceof Error ? e.message : e)); process.exit(1); });
