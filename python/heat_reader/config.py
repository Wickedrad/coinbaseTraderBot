"""Settings of the curve reader: the environment first, command-line flags over it. No secret is needed or read."""
import argparse
import os
import re
from dataclasses import dataclass

DEFAULT_ASSETS = 'BTC,ETH,SOL,XRP'
DEFAULT_WINDOW_BARS = 3000
DEFAULT_BINANCE_API = 'https://data-api.binance.vision/api/v3'
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(PACKAGE_DIR)        # the repo's python/ folder: the oracle package lives beside this one
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
    pack_file: str           # HEAT_PACK_FILE: the traded pack (schema oracle-heat-pack-1)
    meta_dir: str            # HEAT_META_DIR: <COIN>/meta.json, or one live_meta.json keyed by coin
    oracle_path: str         # HEAT_ORACLE_PATH: the folder that holds the oracle package
    assets: list             # HEAT_ASSETS
    refused: list            # coins left out of HEAT_ASSETS (DOGE)
    window_bars: int         # HEAT_WINDOW_BARS: bars per timeframe the engine reads
    binance_api: str         # HEAT_BINANCE_API: the public market data address (tests point this at a local server)
    run: str                 # HEAT_RUN: overrides the run id read from the pack's stamp ('' = read it from the pack)
    once: bool = False


def _args(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog='python3 -m heat_reader', description='Writes the heat calls file the bot reads, once a minute.')
    ap.add_argument('--once', action='store_true', help='one pass, then exit (0 when at least one coin was read)')
    ap.add_argument('--calls-file', help='HEAT_CALLS_FILE')
    ap.add_argument('--reader-dir', help='HEAT_READER_DIR')
    ap.add_argument('--pack-file', help='HEAT_PACK_FILE')
    ap.add_argument('--meta-dir', help='HEAT_META_DIR')
    ap.add_argument('--oracle-path', help='HEAT_ORACLE_PATH')
    ap.add_argument('--assets', help='HEAT_ASSETS')
    ap.add_argument('--window-bars', help='HEAT_WINDOW_BARS')
    ap.add_argument('--binance-api', help='HEAT_BINANCE_API')
    ap.add_argument('--run', help='HEAT_RUN')
    return ap.parse_args(argv)


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
    meta_dir = pick(a.meta_dir, 'HEAT_META_DIR', os.path.join(reader_dir, 'tables'))
    pack_file = pick(a.pack_file, 'HEAT_PACK_FILE', os.path.join(meta_dir, 'traded_pack.json'))
    oracle_path = pick(a.oracle_path, 'HEAT_ORACLE_PATH', PYTHON_DIR)
    assets, refused = parse_assets(pick(a.assets, 'HEAT_ASSETS', DEFAULT_ASSETS))
    raw_window = pick(a.window_bars, 'HEAT_WINDOW_BARS', str(DEFAULT_WINDOW_BARS))
    try:
        window = int(raw_window)
    except ValueError:
        raise ConfigError(f'HEAT_WINDOW_BARS: {raw_window!r} is not a whole number') from None
    if window < MIN_WINDOW_BARS:
        raise ConfigError(f'HEAT_WINDOW_BARS: {window} is below {MIN_WINDOW_BARS} (the engine reads nothing on a shorter window)')
    api = pick(a.binance_api, 'HEAT_BINANCE_API', DEFAULT_BINANCE_API).rstrip('/')
    if not re.match(r'^https?://[^/\s]+', api):
        raise ConfigError('HEAT_BINANCE_API must be an http or https address')
    return Settings(calls_file=os.path.abspath(calls_file), reader_dir=os.path.abspath(reader_dir), pack_file=os.path.abspath(pack_file),
                    meta_dir=os.path.abspath(meta_dir), oracle_path=os.path.abspath(oracle_path), assets=assets, refused=refused,
                    window_bars=window, binance_api=api, run=pick(a.run, 'HEAT_RUN', ''), once=bool(a.once))
