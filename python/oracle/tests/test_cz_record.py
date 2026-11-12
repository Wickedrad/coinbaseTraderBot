"""Coinalyze recorder: network replaced by a fake opener; the key never appears in output or files."""
import gzip
import io
import json
import urllib.error

import pytest

from oracle import cz_record as cz

KEY = 'test-key-not-real'


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(calls, fail_first_429=False):
    state = {'n': 0}

    def opener(req, timeout=60):
        state['n'] += 1
        assert req.get_header('Api_key') == KEY
        calls.append(req.full_url)
        if fail_first_429 and state['n'] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, 'Too Many', {'Retry-After': '31.156'}, None)
        body = [{'symbol': s, 'history': [{'t': 1794441600 + 60 * i, 'c': 1.0} for i in range(3)]} for s in cz.SYMBOLS]
        body.append({'symbol': 'DOGEUSDT_PERP.A', 'history': [{'t': 1}]})
        return Resp(json.dumps(body).encode())
    return opener


def test_pull_writes_every_endpoint_and_never_the_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('COINALYZE_API_KEY', KEY)
    calls, slept = [], []
    path = cz.pull(str(tmp_path), hours=36, now=1794500000, opener=fake_opener(calls, True), sleep=slept.append)
    assert len(calls) == len(cz.PULLS) + 1 and slept[0] == pytest.approx(32.156)
    raw = gzip.open(path, 'rt').read()
    assert KEY not in raw and KEY not in capsys.readouterr().out and all(KEY not in u for u in calls)
    d = json.loads(raw)
    assert set(d['data']) == {f'{e}|{i}' for e, i in cz.PULLS}
    for v in d['data'].values():
        assert set(v) == set(cz.SYMBOLS)                         # DOGE dropped
    assert d['to'] - d['from'] == 36 * 3600 and path.endswith('cz-20261112T1613Z.json.gz')


def test_missing_key_is_loud(monkeypatch, tmp_path):
    monkeypatch.delenv('COINALYZE_API_KEY', raising=False)
    with pytest.raises(SystemExit):
        cz.pull(str(tmp_path))


def test_symbols_never_doge():
    assert all('DOGE' not in s for s in cz.SYMBOLS) and cz.COINS == ('BTC', 'ETH', 'SOL', 'XRP')
