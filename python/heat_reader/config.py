"""Settings of the curve reader: the environment first, command-line flags over it. No secret is needed or read.

Where things are found by default, so the server needs no path setting at all: the reader runs from a release's
python/ folder (deploy/heat-reader.service), and the release holds the oracle package in python/oracle and the
oracle run's packs in research/oracle_heat/latest once the oracle branch is merged to main. HEAT_PACK_DIR and
HEAT_ORACLE_PATH point elsewhere (the check job points them at the pinned oracle commit).
"""
import argparse
import os
import re
from dataclasses import dataclass

DEFAULT_ASSETS = 'BTC,ETH,SOL,XRP'
DEFAULT_WINDOW_BARS = 3000
DEFAULT_BINANCE_API = 'https://data-api.binance.vision/api/v3'
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(PACKAGE_DIR)        # the repo's python/ folder: the oracle package lives beside this one
REPO_DIR = os.path.dirname(PYTHON_DIR)           # the release (or checkout) itself
DEFAULT_PACK_DIR = os.path.join(REPO_DIR, 'research', 'oracle_heat', 'latest')
DEFAULT_MAX_RANK = 40                            # the traded pack's heat ladder: rank_coin 1..40
MIN_WINDOW_BARS = 300                            # the engine gives no reading on a timeframe's first 250 bars
LOG_DAYS = 14                                    # daily replay logs kept beside the calls file


class ConfigError(Exception):
    """A setting the reader cannot run with. The message is plain text for the log and the calls file."""


def is_doge(coin: str) -> bool:
    """DOGE is not traded anywhere in this project (no table exists for it), under any spelling of the name."""
    return str(coin).strip().upper().startswith('DOGE')


def parse_assets(text: str) -> tuple:
    """(coins to read, coins refused). Names become upper case; DOGE is refused even when listed; a name that is not
    plain letters and digits is an error, because the name goes into file names and the Binance symbol."""
    coins, refused = [], []
    for raw in str(text).split(','):
        name = raw.strip().upper()
        if not name:
            continue
        if is_doge(name):
            refused.append(name)
            continue
        if not re.fullmatch(r'[A-Z0-9]{2,10}', name):
            raise ConfigError(f'HEAT_ASSETS: {raw.strip()!r} is not a coin name')
        if name not in coins:
            coins.append(name)
    if not coins:
        raise ConfigError('HEAT_ASSETS names no coin the reader may read')
    return coins, refused


@dataclass
class Settings:
    calls_file: str          # HEAT_CALLS_FILE: the file the bot reads
    reader_dir: str          # HEAT_READER_DIR: the minute cache and status.json
    pack_dir: str            # HEAT_PACK_DIR: traded_pack.json, pair_pack.json, clock_pack.json, live_meta.json and the perp packs
    oracle_path: str         # HEAT_ORACLE_PATH: the folder that holds the oracle package
    assets: list             # HEAT_ASSETS
    refused: list            # coins left out of HEAT_ASSETS (DOGE)
    window_bars: int         # HEAT_WINDOW_BARS: bars per timeframe the engine reads
    binance_api: str         # HEAT_BINANCE_API: the public market data address (tests point this at a local server)
    run: str                 # HEAT_RUN: overrides the run id read from the pack's stamp ('' = read it from the pack)
    max_rank: int = DEFAULT_MAX_RANK   # HEAT_READER_MAX_RANK: traded pack rows with a higher rank_coin are never published
    clock_pack: bool = False # HEAT_CLOCK_PACK: also load clock_pack.json (off until the oracle thread says it is worth it)
    perp_packs: bool = True  # HEAT_PERP_PACKS: also load perp_pack.json and perp_pair_pack.json (h240 and h1440 rows for perps)
    once: bool = False


def _args(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog='python3 -m heat_reader', description='Writes the heat calls file the bot reads, once a minute.')
    ap.add_argument('--once', action='store_true', help='one pass, then exit (0 when at least one coin was read)')
    ap.add_argument('--calls-file', help='HEAT_CALLS_FILE')
    ap.add_argument('--reader-dir', help='HEAT_READER_DIR')
    ap.add_argument('--pack-dir', help='HEAT_PACK_DIR')
    ap.add_argument('--oracle-path', help='HEAT_ORACLE_PATH')
    ap.add_argument('--assets', help='HEAT_ASSETS')
    ap.add_argument('--window-bars', help='HEAT_WINDOW_BARS')
    ap.add_argument('--binance-api', help='HEAT_BINANCE_API')
    ap.add_argument('--run', help='HEAT_RUN')
    ap.add_argument('--max-rank', help='HEAT_READER_MAX_RANK')
    ap.add_argument('--clock-pack', help='HEAT_CLOCK_PACK (true or false)')
    ap.add_argument('--perp-packs', help='HEAT_PERP_PACKS (true or false)')
    return ap.parse_args(argv)


def parse_bool(text: str, name: str) -> bool:
    v = str(text).strip().lower()
    if v in ('true', '1', 'yes', 'on'):
        return True
    if v in ('false', '0', 'no', 'off'):
        return False
    raise ConfigError(f'{name}: {text!r} is neither true nor false')


def load(argv=None, env=None) -> Settings:
    """Settings from the environment, with flags over it. Raises ConfigError with a plain reason."""
    env = os.environ if env is None else env
    a = _args([] if argv is None else argv)

    def pick(flag, name, default):
        v = flag if flag not in (None, '') else env.get(name)
        return default if v in (None, '') else str(v)

    data_dir = env.get('DATA_DIR') or './data'           # the bot's own default, so both sides agree on the file
    calls_file = pick(a.calls_file, 'HEAT_CALLS_FILE', os.path.join(data_dir, 'heat_calls.json'))
    reader_dir = pick(a.reader_dir, 'HEAT_READER_DIR', os.path.join(data_dir, 'heat_reader'))
    pack_dir = pick(a.pack_dir, 'HEAT_PACK_DIR', DEFAULT_PACK_DIR)
    oracle_path = pick(a.oracle_path, 'HEAT_ORACLE_PATH', PYTHON_DIR)
    assets, refused = parse_assets(pick(a.assets, 'HEAT_ASSETS', DEFAULT_ASSETS))
    raw_window = pick(a.window_bars, 'HEAT_WINDOW_BARS', str(DEFAULT_WINDOW_BARS))
    try:
        window = int(raw_window)
    except ValueError:
        raise ConfigError(f'HEAT_WINDOW_BARS: {raw_window!r} is not a whole number') from None
    if window < MIN_WINDOW_BARS:
        raise ConfigError(f'HEAT_WINDOW_BARS: {window} is below {MIN_WINDOW_BARS} (the engine reads nothing on a shorter window)')
    raw_rank = pick(a.max_rank, 'HEAT_READER_MAX_RANK', str(DEFAULT_MAX_RANK))
    try:
        max_rank = int(raw_rank)
    except ValueError:
        raise ConfigError(f'HEAT_READER_MAX_RANK: {raw_rank!r} is not a whole number') from None
    if max_rank < 1:
        raise ConfigError(f'HEAT_READER_MAX_RANK: {max_rank} is below 1 (no row could be published)')
    clock = parse_bool(pick(a.clock_pack, 'HEAT_CLOCK_PACK', 'false'), 'HEAT_CLOCK_PACK')
    perp = parse_bool(pick(a.perp_packs, 'HEAT_PERP_PACKS', 'true'), 'HEAT_PERP_PACKS')
    api = pick(a.binance_api, 'HEAT_BINANCE_API', DEFAULT_BINANCE_API).rstrip('/')
    if not re.match(r'^https?://[^/\s]+', api):
        raise ConfigError('HEAT_BINANCE_API must be an http or https address')
    return Settings(calls_file=os.path.abspath(calls_file), reader_dir=os.path.abspath(reader_dir), pack_dir=os.path.abspath(pack_dir),
                    oracle_path=os.path.abspath(oracle_path), assets=assets, refused=refused, window_bars=window, binance_api=api,
                    run=pick(a.run, 'HEAT_RUN', ''), max_rank=max_rank, clock_pack=clock, perp_packs=perp, once=bool(a.once))


def status_path(calls_file: str) -> str:
    """The sidecar beside the calls file (heat_calls.json gives heat_calls.status.json): per coin, the rows the reader
    asks for and the rows it leaves out, by reason. The bot finds it from HEAT_CALLS_FILE alone."""
    base = calls_file[:-5] if calls_file.endswith('.json') else calls_file
    return base + '.status.json'
