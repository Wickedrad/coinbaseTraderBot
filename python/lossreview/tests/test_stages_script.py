"""The stages script (.github/scripts/loss_review_stages.sh) end to end with a stand-in rclone over a local folder as "Drive"."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPT = os.path.join(ROOT, '.github', 'scripts', 'loss_review_stages.sh')

FAKE_RCLONE = r'''#!/usr/bin/env python3
import fnmatch, os, re, shutil, sys
a = sys.argv[1:]
cmd = a[0]
def rx(p):
    out, i = '', 0
    while i < len(p):
        if p.startswith('**', i): out += '.*'; i += 2
        elif p[i] == '*': out += '[^/]*'; i += 1
        elif p[i] == '?': out += '[^/]'; i += 1
        else: out += re.escape(p[i]); i += 1
    return re.compile('^' + out + '$')
if cmd == 'lsf':
    d = a[1]
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)): print(n)
    sys.exit(0)
if cmd == 'size':
    print('Total size: 0 B'); sys.exit(0)
if cmd == 'copy':
    src, dst, inc = a[1], a[2], []
    i = 3
    while i < len(a):
        if a[i] == '--include': inc.append(rx(a[i + 1])); i += 2
        elif a[i] in ('--exclude', '--transfers'): i += 2
        else: i += 1
    for base, _, files in os.walk(src):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), src)
            if inc and not any(r.match(rel) for r in inc): continue
            to = os.path.join(dst, rel); os.makedirs(os.path.dirname(to), exist_ok=True)
            shutil.copyfile(os.path.join(base, f), to)
    sys.exit(0)
sys.exit(2)
'''


def trips(day, n=6):
    t0 = 1_700_000_000
    return ''.join(json.dumps({'ticker': 'KXBTC15M-SECRET%d' % i, 'entry_t': t0 + i * 60, 'closed_t': t0 + i * 60 + 500, 'entry_px': 0.5, 'count': 20,
                               'pnl': -1.0 - i, 'class': 'WRONG_SIDE', 'fidelity_flag': False, 'stake': 10.0}) + '\n' for i in range(n))


class StagesScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.drive = os.path.join(self.tmp, 'drive')
        self.base = os.path.join(self.drive, 'derived', 'loss-review')
        os.makedirs(os.path.join(self.base, 'days'))
        os.makedirs(os.path.join(self.base, 'work', 'other-day'))
        self.day = '2023-11-14'
        with open(os.path.join(self.base, 'days', 'trips-%s.jsonl' % self.day), 'w') as fh:
            fh.write(trips(self.day))
        with open(os.path.join(self.base, 'work', 'other-day', 'prompt-keep.txt'), 'w') as fh:
            fh.write('not pulled')
        bin_ = os.path.join(self.tmp, 'bin')
        os.makedirs(bin_)
        p = os.path.join(bin_, 'rclone')
        with open(p, 'w') as fh:
            fh.write(FAKE_RCLONE)
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        self.env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ['PATH'], DRIVE_ROOT=self.drive, RUNNER_TEMP=self.tmp)
        for k in ('LR_DAY', 'LR_STAGES', 'LR_USAGE', 'LR_RESPONSES', 'LR_SINCE', 'LR_UNTIL'):
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, **kw):
        env = dict(self.env, **kw)
        return subprocess.run(['bash', SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True)

    def test_rejects_what_it_does_not_know_before_touching_drive(self):
        for kw in ({'LR_DAY': '2023-11-14; rm -rf /'}, {'LR_DAY': self.day, 'LR_STAGES': 'sweep;ls'}, {'LR_DAY': self.day, 'LR_STAGES': '*'},
                   {'LR_DAY': self.day, 'LR_STAGES': ' , '}, {'LR_DAY': self.day, 'LR_USAGE': 'tag:1:2'}, {'LR_DAY': self.day, 'LR_USAGE': 'oops:1:2:3'},
                   {'LR_DAY': self.day, 'LR_STAGES': 'window', 'LR_UNTIL': '12:99:99:1'}, {}):
            r = self.run_script(**kw)
            self.assertNotEqual(r.returncode, 0, kw)
            self.assertIn('::error::', r.stderr, kw)

    def test_read_only_stages_put_nothing_back(self):
        r = self.run_script(LR_DAY=self.day, LR_STAGES='pending,status')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('LOSSLOOP pending', r.stdout)
        self.assertIn('LOSSLOOP canary {"ok": true', r.stdout)
        self.assertIn('nothing put back', r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.base, 'registry.jsonl')))

    def test_window_usage_and_window_put_only_the_allowed_files_and_the_log_has_no_ticker_or_dollar(self):
        r = self.run_script(LR_DAY=self.day, LR_STAGES='window', LR_UNTIL='23:59', LR_USAGE='tag:100:20:5;audit:1:1:1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('SECRET', r.stdout + r.stderr)
        self.assertNotIn('"net"', r.stdout)
        saved = [f for f in os.listdir(os.path.join(self.base, 'work', self.day))]
        self.assertTrue(any(f.startswith('window-') for f in saved), saved)
        lines = open(os.path.join(self.base, 'usage.jsonl')).read().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.base, 'work'))), sorted([self.day, 'other-day']))
        self.assertEqual(open(os.path.join(self.base, 'work', 'other-day', 'prompt-keep.txt')).read(), 'not pulled')   # not pulled, not touched
        self.assertEqual(sorted(os.listdir(os.path.join(self.base, 'days'))), ['trips-%s.jsonl' % self.day])

    def test_responses_stage_and_a_failing_stage_stops_before_the_put(self):
        r = self.run_script(LR_DAY=self.day, LR_STAGES='prepare-tags')
        self.assertEqual(r.returncode, 0, r.stderr)
        wd = os.path.join(self.base, 'work', self.day)
        self.assertTrue(os.path.exists(os.path.join(wd, 'tag-00.prompt.txt')))
        r = self.run_script(LR_DAY=self.day, LR_STAGES='apply-tags', LR_RESPONSES=json.dumps({'tag-00': [{'i': 0, 'tags': ['late_entry']}]}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(wd, 'tag-00.response.json')))
        self.assertIn('LOSSLOOP responses', r.stdout)
        before = sorted(os.listdir(wd))
        r = self.run_script(LR_DAY=self.day, LR_STAGES='apply-tags', LR_RESPONSES=json.dumps({'tag-07': []}))     # no such prompt: the stage fails
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(sorted(os.listdir(wd)), before)
        r = self.run_script(LR_DAY='2023-11-20', LR_STAGES='done')                  # no trip file for that day: done refuses
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.base, 'work', '2023-11-20', 'done.json')))

    def test_an_empty_drive_folder_is_an_error(self):
        shutil.rmtree(os.path.join(self.base, 'days'))
        r = self.run_script(LR_DAY=self.day, LR_STAGES='status')
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
