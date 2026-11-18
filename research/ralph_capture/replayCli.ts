/** Command line for replayDecisions.ts. RESEARCH ONLY.
 *
 *    node --import tsx research/ralph_capture/replayCli.ts JOURNAL      (exit 0 = chain intact and every stored decision reproduced, 1 = not, 2 = none)
 *
 *  Run verify_journal.py on the same file too, and ask for both to pass: this tool does not check the footer's record and frame counts,
 *  clocks, epochs, the frames' sequence continuity or an anchor. */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { replayDecisionFile, replayPassed } from './replayDecisions';

const root = path.resolve(path.dirname(process.argv[1] ?? '.'), '..', '..');
/** The files decideHeat's result depends on (heatLane.ts imports the rest only for logging and file saving). */
const DECIDE_FILES = ['bot/heat/heatLane.ts', 'bot/heat/heatBook.ts', 'bot/plan/planRatchet.ts', 'bot/util/num.ts'];

const git = (args: string[]): string | null => {
  try { return execFileSync('git', ['-C', root, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { return null; }
};

/** Which code the replay ran: the commit of THIS checkout (not the caller's directory), whether those files differ from it, and a hash of
 *  each file decideHeat depends on, so two replays on different machines can be compared byte for byte. */
function codeIdentity() {
  const files: Record<string, string | null> = {};
  for (const f of DECIDE_FILES) { try { files[f] = createHash('sha256').update(fs.readFileSync(path.join(root, f))).digest('hex'); } catch { files[f] = null; } }
  const dirty = git(['status', '--porcelain', '--', ...DECIDE_FILES]);
  return { checkout: root, commit: git(['rev-parse', 'HEAD']), decide_files_modified: dirty === null ? null : dirty.length > 0, decide_files_sha256: files };
}

async function main(): Promise<void> {
  const file = process.argv[2];
  if (!file) { console.error('usage: replayCli.ts JOURNAL'); process.exit(64); }
  const r = await replayDecisionFile(file);
  console.log(JSON.stringify({
    file, ...r, passed: replayPassed(r),
    replayed_with: codeIdentity(),
    chain_checked_here: true,
    verifier_checks_included: false,
    anchor_checked_here: false,
    receipts_authenticated: false,
    books_bound_to_decisions: false,
    caveat: 'passed means: unbroken chain, and the decideHeat in the checkout above gives the stored result for the stored input. It does not show that the server ran this code (journalRelease is the release folder it ran from; compare it with the commit in the deploy log), that the receipts are authentic, or that the stored markets match the frames. verify_journal.py must pass as well.',
  }, null, 1));
  process.exit(r.decisions === 0 ? 2 : replayPassed(r) ? 0 : 1);
}

main().catch((e) => { console.error(String(e instanceof Error ? e.message : e)); process.exit(1); });
