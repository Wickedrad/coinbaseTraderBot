/** Starts the raw frame journal inside a running bot, from environment variables. RESEARCH ONLY.
 *
 *  bot/main.ts loads this module only when RALPH_RAW_TAP=1, so with the variable unset nothing here is even imported.
 *  It observes the Kalshi socket and writes a private file; it places no order and touches no trading state. It refuses to
 *  start in live mode (unless RALPH_RAW_TAP_ALLOW_LIVE=1), when the directory is missing or relative, or when anything is
 *  wrong with the settings: in every such case the bot just runs without it.
 *
 *    RALPH_RAW_TAP=1                  switch on
 *    RALPH_RAW_TAP_DIR=/abs/path      existing or creatable directory for the journal and anchor files (required)
 *    RALPH_RAW_TAP_MAX_MB=500         stop at this size (1-5000)
 *    RALPH_RAW_TAP_HOURS=24           stop after this long (0.1-168)
 *
 *  A stopped capture is not restarted until the bot restarts; each start writes a new file, never touching an old one. */
import fs from 'node:fs';
import path from 'node:path';
import { logger } from '../../bot/util/log';
import type { KalshiWs } from '../../bot/kalshi/ws';
import { RawFrameTap } from './rawTap';

const log = logger('ralph-tap');

export interface AttachContext { mode: string; wsUrl: string }
export interface AttachTuning { pollMs?: number; maxBytes?: number; maxMs?: number }
export interface AttachedTap { tap: RawFrameTap; file: string; stop(): Promise<void> }

const num = (v: string | undefined, dflt: number, lo: number, hi: number): number => {
  const n = v === undefined || v === '' ? dflt : Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt;
};

/** The folder the process runs from (the deploy's release folder behind the `current` link): the only code identity a receipt replay
 *  can compare with the commit it replays under. Not secret; 'unknown' when it cannot be read. */
function releaseName(): string {
  try { return path.basename(fs.realpathSync(process.cwd())); } catch { return 'unknown'; }
}

export function attachRawTapFromEnv(ws: KalshiWs, env: NodeJS.ProcessEnv, ctx: AttachContext, tuning: AttachTuning = {}): AttachedTap | undefined {
  if (env.RALPH_RAW_TAP !== '1') return undefined;
  if (ctx.mode === 'live' && env.RALPH_RAW_TAP_ALLOW_LIVE !== '1') { log.warn('raw frame journal not started: live mode'); return undefined; }
  const dir = env.RALPH_RAW_TAP_DIR;
  if (!dir || !path.isAbsolute(dir)) { log.warn('raw frame journal not started: RALPH_RAW_TAP_DIR must be an absolute path'); return undefined; }
  const maxMb = num(env.RALPH_RAW_TAP_MAX_MB, 500, 1, 5000);
  const hours = num(env.RALPH_RAW_TAP_HOURS, 24, 0.1, 168);
  const maxBytes = tuning.maxBytes ?? maxMb * 1024 * 1024;
  const maxMs = tuning.maxMs ?? hours * 3_600_000;
  let u: URL;
  try { u = new URL(ctx.wsUrl); } catch { log.warn('raw frame journal not started: unreadable websocket URL'); return undefined; }
  let tap: RawFrameTap;
  let file: string;
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    file = path.join(dir, `kalshi-ws-${stamp}.journal`);
    tap = new RawFrameTap({
      file, anchorFile: path.join(dir, `kalshi-ws-${stamp}.anchor`), anchorEvery: 500, maxPendingBytes: 8 * 1024 * 1024,
      onAnchor: (a) => log.info('journal checkpoint', a),
      config: { tool: 'ralph_capture/attach', schema: 1, ws_host: u.host, ws_path: u.pathname, mode: ctx.mode, max_bytes: maxBytes, max_ms: maxMs, private_channels_redacted: true, release: releaseName() },
    });
  } catch (e) { log.warn(`raw frame journal not started: ${String(e)}`); return undefined; }
  const started = Date.now();
  ws.setRawSink(tap);
  let stopped: Promise<void> | undefined;
  const stop = (reason = 'stopped'): Promise<void> => {
    if (stopped) return stopped;
    stopped = (async () => {
      clearInterval(timer);
      // let a socket close already under way reach the journal before the footer
      await new Promise<void>((r) => setTimeout(r, reason === 'stopped' ? 300 : 0));
      ws.setRawSink(undefined);
      await tap.close(reason);
      log.info('raw frame journal closed', { file, reason, ...tap.status() });
    })();
    return stopped;
  };
  const timer = setInterval(() => {
    const st = tap.status();
    if (st.failed) void stop('failed');
    else if (st.bytes >= maxBytes) void stop('size_cap');
    else if (Date.now() - started >= maxMs) void stop('time_cap');
  }, tuning.pollMs ?? 1000);
  timer.unref();
  log.info('raw frame journal started', { file, maxMb, hours, mode: ctx.mode });
  return { tap, file, stop: () => stop('stopped') };
}
