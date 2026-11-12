/** One temp folder per test file run. Imported first by tests/helpers.ts and by each test file that makes temp folders
 *  without helpers (a new such file should import it too). The first process to load it makes a `bot-test-run-*` folder
 *  under the system temp folder, points TMPDIR at it (so tmpDir(), every mkdtemp under os.tmpdir() and the shell or Python
 *  scripts a test spawns all land inside it) and removes it when that process exits. A process that inherits the folder
 *  (a node script a test spawns that loads this file too) uses it and leaves the removal to the test's process, so a spawned
 *  script's files outlive it for the test to read. Before this, every run left its folders in /tmp (about 54,000 after a
 *  night of runs, which filled a cloud session's disk). A test process killed by a signal still leaves its one folder. */
import fs from 'fs';
import os from 'os';
import path from 'path';

const KEY = 'BOT_TEST_TMP';
const inherited = process.env[KEY];
if (inherited && fs.existsSync(inherited)) {
  process.env.TMPDIR = inherited;
} else {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bot-test-run-'));
  process.env[KEY] = dir;
  process.env.TMPDIR = dir;
  process.on('exit', () => {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      /* best effort: a folder left behind is the old behaviour */
    }
  });
}
