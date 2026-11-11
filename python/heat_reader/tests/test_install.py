"""deploy/heat_reader_install.sh and deploy/heat-reader.service, run with a throwaway home and stand-ins for sudo,
systemctl and journalctl (they only write down what they were asked): what the script does with HEAT_LANE on and
off, that a second run changes nothing, and that it never touches the bot's service or its env file."""
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

from conftest import FIXTURES, PACKAGE, REPO

SCRIPT = os.path.join(REPO, 'deploy', 'heat_reader_install.sh')
UNIT = os.path.join(REPO, 'deploy', 'heat-reader.service')
pytestmark = pytest.mark.skipif(shutil.which('bash') is None or not sys.platform.startswith('linux'), reason='needs bash on Linux')

STUB = '''#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case "$(basename "$0")" in
  sudo) exec "$@" ;;
  systemctl) case "$1" in is-active) [ -f "$STUB_DIR/active" ] ;; show) echo 4242 ;; restart) touch "$STUB_DIR/active" ;; stop|disable) rm -f "$STUB_DIR/active" ;; esac ;;
esac
exit $?
'''
# Stands in for the venv's python once the venv "exists": imports load, pip and compileall succeed.
FAKE_PY = '#!/usr/bin/env bash\necho "venv-python $*" >> "$STUB_LOG"\nexit 0\n'


class Box:
    def __init__(self, tmp):
        self.home, self.bin, self.units = tmp / 'home', tmp / 'bin', tmp / 'units'
        self.rel = self.home / 'releases' / 'r1'
        self.log = tmp / 'calls.log'
        self.packs = self.rel / 'research' / 'oracle_heat' / 'latest'
        for d in (self.bin, self.units, self.home / 'bot', self.rel / 'deploy', self.rel / 'python' / 'oracle', self.rel / 'python' / 'heat_reader', self.packs):
            os.makedirs(d)
        for name in ('sudo', 'systemctl', 'journalctl'):
            (self.bin / name).write_text(STUB)
            os.chmod(self.bin / name, 0o755)
        shutil.copy(SCRIPT, self.rel / 'deploy')
        shutil.copy(UNIT, self.rel / 'deploy')
        shutil.copy(os.path.join(PACKAGE, 'requirements.txt'), self.rel / 'python' / 'heat_reader')
        for name in ('traded_pack.json', 'pair_pack.json', 'clock_pack.json', 'live_meta.json'):   # the oracle run's packs, as the release ships them
            shutil.copy(os.path.join(FIXTURES, name), self.packs)
        (self.rel / 'python' / 'heat_reader' / 'cli.py').write_text('')
        (self.rel / 'python' / 'oracle' / 'heat_live.py').write_text('')
        self.venv = self.home / 'bot' / '.venv-heat-reader'

    def env(self, text):
        (self.home / 'bot' / 'bot.env').write_text(text)

    def fake_venv(self):
        """A venv that is already built for these pins and this Python."""
        os.makedirs(self.venv / 'bin')
        (self.venv / 'bin' / 'python').write_text(FAKE_PY)
        os.chmod(self.venv / 'bin' / 'python', 0o755)
        pyv = subprocess.run([sys.executable, '-c', 'import platform; print(platform.python_version(), platform.machine())'], capture_output=True, text=True).stdout.strip()
        sha = hashlib.sha256(open(os.path.join(PACKAGE, 'requirements.txt'), 'rb').read()).hexdigest()
        (self.venv / '.heat-reader-stamp').write_text(f'{sha} {pyv}\n')

    def run(self):
        self.log.write_text('')
        # PIP_NO_INDEX: pip never reaches out from a test; a wheel that is not already here cannot be installed
        env = {'HOME': str(self.home), 'PATH': f'{self.bin}:{os.path.dirname(sys.executable)}:{os.environ.get("PATH", "")}', 'STUB_LOG': str(self.log),
               'STUB_DIR': str(self.bin), 'HEAT_READER_UNIT_DIR': str(self.units), 'PIP_NO_INDEX': '1'}
        p = subprocess.run(['bash', str(self.rel / 'deploy' / 'heat_reader_install.sh')], env=env, capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout + p.stderr, self.log.read_text()


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def test_lane_off_installs_nothing_and_stops_a_running_reader(box):
    box.env('TRADING_MODE=paper\n')
    rc, out, log = box.run()
    assert rc == 0 and 'HEAT_LANE is not true' in out and 'nothing installed' in out and log == ''
    assert not box.venv.exists() and os.listdir(box.units) == [] and not (box.home / 'bot' / 'heat-reader.env').exists()
    # a unit from an earlier time is stopped and disabled, never started
    (box.units / 'heat-reader.service').write_text('old')
    for text in ('HEAT_LANE=false\n', 'HEAT_LANE=true\nHEAT_LANE=false\n', '#HEAT_LANE=true\n'):
        box.env(text)
        rc, out, log = box.run()
        assert rc == 0 and 'stopped and disabled' in out and log.splitlines() == ['sudo systemctl disable --now heat-reader', 'systemctl disable --now heat-reader']


def test_lane_on_installs_starts_and_is_idempotent(box):
    secret = 'KALSHI_API_KEY_ID=never-copy-this\nDASHBOARD_PASSWORD=nor-this\n'
    box.env(secret + 'HEAT_LANE=true\nHEAT_ASSETS=BTC,ETH\nHEAT_WINDOW_BARS="3000"\nHEAT_TOP_N=10\nHEAT_READER_MAX_RANK=20\nHEAT_CLOCK_PACK=false\n')
    box.fake_venv()
    before = (box.home / 'bot' / 'bot.env').read_text()
    rc, out, log = box.run()
    assert rc == 0, out
    assert 'venv unchanged' in out and 'unit installed' in out and f'running (pid 4242), packs from {box.packs}.' in out
    unit = (box.units / 'heat-reader.service').read_text()
    home = str(box.home)
    assert f'WorkingDirectory={home}/bot/current/python' in unit and f'ExecStart={home}/bot/.venv-heat-reader/bin/python -m heat_reader' in unit
    assert f'ReadWritePaths={home}/bot/data\n' in unit and '/home/ubuntu' not in unit and f'User={subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()}\n' in unit
    assert f'EnvironmentFile=-{home}/bot/heat-reader.env' in unit and 'bot.env' not in unit.split('[Unit]')[1]      # the unit never loads bot.env
    # the packs and the oracle code are read from the release behind ~/bot/current: code and curves move together
    assert f'Environment=HEAT_PACK_DIR={home}/bot/current/research/oracle_heat/latest\n' in unit and f'Environment=HEAT_ORACLE_PATH={home}/bot/current/python\n' in unit
    for line in ('MemoryMax=220M', 'MemoryHigh=180M', 'OOMScoreAdjust=900', 'Nice=10', 'CPUQuota=50%', 'Restart=always', 'RestartSec=30'):
        assert f'\n{line}\n' in unit
    # only the reader's own settings are copied out of bot.env: no secret, no lane setting
    renv = (box.home / 'bot' / 'heat-reader.env').read_text()
    assert [x for x in renv.splitlines() if not x.startswith('#')] == ['HEAT_ASSETS=BTC,ETH', 'HEAT_WINDOW_BARS=3000', 'HEAT_READER_MAX_RANK=20', 'HEAT_CLOCK_PACK=false']
    assert not (box.home / 'bot' / 'data' / 'heat_reader').exists()           # nothing is copied out of the release
    sysctl = [x for x in log.splitlines() if x.startswith('systemctl ')]
    assert sysctl == ['systemctl daemon-reload', 'systemctl enable heat-reader', 'systemctl restart heat-reader', 'systemctl is-active --quiet heat-reader',
                      'systemctl show -p MainPID --value heat-reader']
    assert 'kalshi-bot' not in log and (box.home / 'bot' / 'bot.env').read_text() == before          # the bot's service and env file are left alone
    assert 'never-copy-this' not in out + log + renv + unit and 'nor-this' not in out + log + renv + unit

    # a second run with nothing changed: no rebuild, no new unit, the same files; only the restart
    rc, out2, log2 = box.run()
    assert rc == 0 and 'venv unchanged' in out2 and 'unit installed' not in out2
    assert 'daemon-reload' not in log2 and 'pip install' not in log2 and 'systemctl restart heat-reader' in log2
    assert (box.units / 'heat-reader.service').read_text() == unit and (box.home / 'bot' / 'heat-reader.env').read_text() == renv

    # the clock pack asked for: the release ships it, so nothing changes but the setting; without it the reader is not started
    box.env('HEAT_LANE=true\nHEAT_CLOCK_PACK=TRUE\n')
    rc, out3, _ = box.run()
    assert rc == 0 and 'HEAT_CLOCK_PACK=TRUE' in (box.home / 'bot' / 'heat-reader.env').read_text()
    os.unlink(box.packs / 'clock_pack.json')
    rc, out3, log3 = box.run()
    assert rc == 1 and f'no clock_pack.json in {box.packs}' in out3 and 'restart' not in log3

    # the lane switched off again: stopped and disabled, files left in place
    box.env('HEAT_LANE=false\n')
    rc, out4, log4 = box.run()
    assert rc == 0 and 'stopped and disabled' in out4 and 'systemctl disable --now heat-reader' in log4 and 'restart' not in log4


def test_lane_on_but_not_installable_exits_one(box):
    box.env('HEAT_LANE=1\n')
    os.unlink(box.rel / 'python' / 'oracle' / 'heat_live.py')
    rc, out, log = box.run()
    assert rc == 1 and 'does not ship python/oracle' in out and 'The bot is not affected' in out and 'restart' not in log
    (box.rel / 'python' / 'oracle' / 'heat_live.py').write_text('')
    # a release without the packs (the oracle branch not merged, or the deploy not copying research/oracle_heat/latest)
    for name in ('traded_pack.json', 'pair_pack.json', 'live_meta.json'):
        shutil.move(box.packs / name, box.packs / f'{name}.away')
        rc, out, log = box.run()
        assert rc == 1 and f'no {name} in {box.packs}: the release must ship' in out and 'restart' not in log
        shutil.move(box.packs / f'{name}.away', box.packs / name)
    # HEAT_PACK_DIR in bot.env is where the packs are looked for then
    box.env(f'HEAT_LANE=1\nHEAT_PACK_DIR={box.home}/elsewhere\n')
    rc, out, log = box.run()
    assert rc == 1 and f'no traded_pack.json in {box.home}/elsewhere' in out
    # a calls file outside ~/bot/data, or a relative one, is refused: the bot and the reader would not meet
    for bad in ('HEAT_CALLS_FILE=./data/heat_calls.json', 'HEAT_CALLS_FILE=/var/tmp/heat_calls.json'):
        box.env(f'HEAT_LANE=true\n{bad}\n')
        rc, out, log = box.run()
        assert rc == 1 and 'must be a full path under' in out and 'restart' not in log
    # the pinned wheels cannot be installed (here: a pin pip cannot find, with no index to look in): no venv is left, exit 1
    box.env(f'HEAT_LANE=true\nHEAT_CALLS_FILE={box.home}/bot/data/heat_calls.json\n')
    (box.rel / 'python' / 'heat_reader' / 'requirements.txt').write_text('heat-reader-no-such-wheel==0.0.0 --hash=sha256:' + '0' * 64 + '\n')
    rc, out, log = box.run()
    assert rc == 1 and 'pip could not install the pinned wheels' in out and not box.venv.exists() and 'systemctl restart' not in log
    # pip installs, but what it installed does not load (here: pins that name nothing, so no TA-Lib): no venv is left, exit 1
    (box.rel / 'python' / 'heat_reader' / 'requirements.txt').write_text('# no pins\n')
    rc, out, log = box.run()
    assert rc == 1 and 'the installed wheels do not load' in out and not box.venv.exists() and 'systemctl restart' not in log
    # the reader does not stay up after the restart: the journal is shown and the exit code says so
    shutil.copy(os.path.join(PACKAGE, 'requirements.txt'), box.rel / 'python' / 'heat_reader')
    box.fake_venv()
    stub = (box.bin / 'systemctl').read_text().replace('restart) touch "$STUB_DIR/active" ;;', 'restart) : ;;')
    (box.bin / 'systemctl').write_text(stub)
    rc, out, log = box.run()
    assert rc == 1 and 'the reader did not stay up' in out and 'journalctl -u heat-reader -n 30 --no-pager' in log


def test_unit_file_rules():
    unit = open(UNIT).read()
    assert 'kalshi-bot' not in unit.replace('Kalshi bot reads', '') and 'EnvironmentFile=/home/ubuntu/bot/bot.env' not in unit
    assert unit.count('ExecStart=') == 1 and 'WantedBy=multi-user.target' in unit
    script = open(SCRIPT).read()
    assert '--require-hashes' in script and '--only-binary=:all:' in script
    assert 'systemctl restart kalshi-bot' not in script and 'systemctl stop kalshi-bot' not in script
