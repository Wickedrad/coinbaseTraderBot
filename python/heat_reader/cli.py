"""Command line of the curve reader: python3 -m heat_reader [--once] [flags over the HEAT_* settings]."""
import sys

from heat_reader import config
from heat_reader.reader import Reader


def main(argv=None) -> int:
    """0 = stopped on request, or --once read at least one coin. 1 = no coin could be read (--once), or ten minutes
    passed without a good pass (the loop). 2 = a setting the reader cannot run with."""
    try:
        s = config.load(sys.argv[1:] if argv is None else argv)
    except config.ConfigError as e:
        print(f'heat-reader: {e}', flush=True)
        return 2
    log = lambda text: print(text, flush=True)
    for name in s.refused:
        log(f'heat-reader: {name} is in HEAT_ASSETS and is refused (never DOGE)')
    log(f'heat-reader: coins {",".join(s.assets)}; window {s.window_bars} bars; calls file {s.calls_file}; cache {s.reader_dir}; '
        f'pack {s.pack_file}; metas {s.meta_dir}; oracle {s.oracle_path}')
    reader = Reader(s, log=log)
    if not s.once:
        return reader.run()
    try:
        obj = reader.pass_once()
    except Exception as e:                # the calls file could not be written
        log(f'heat-reader pass failed: {type(e).__name__}: {e}'[:300])
        return 1
    return 0 if any(c['ok'] for c in obj['coins'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
