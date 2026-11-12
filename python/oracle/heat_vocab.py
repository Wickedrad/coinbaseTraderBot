"""OR-HM1 reading vocabulary (python/oracle/prereg/OR-HM1.md, Amendment 1): every TA-Lib indicator that yields a
signal, turned into a normalised value series per bar (known at that bar's close), plus the two-state and candlestick
readings. heat.py turns each value series into a decile curve, a five-zone reading (bottom 2%, 2-10%, middle, 90-98%,
top 2% of its own split-A distribution) and, where zero means something, an above/below-zero reading.

Normalisation types (so one set of zone edges fits 2020-2026 and every coin):
  osc     bounded or self-normalised oscillator, used as is
  atr     price units -> divided by ATR(14)
  dist    an overlay line (average, band, stop) -> (close - line) / ATR(14)
  pct     percent of price -> divided by NATR(14)
  cum     a running total (OBV, A/D ...) -> its 10-bar change over the rolling std (200) of that change
  z       awkward scale -> rolling z-score over 500 bars
  regime  a volatility level -> ratio to its own 200-bar mean
  vol     volume units -> divided by the 20-bar mean volume

Left out on purpose (listed in meta.json 'excluded'): math operators / transforms (not signals); exact duplicates
(ROCP, ROCR, ROCR100, MACDEXT, MACDFIX, MA, MAVP, SAREXT, VAR, KSTEXT, LINEARREG_ANGLE, LINEARREG_INTERCEPT,
PLUS_DM, MINUS_DM, BBANDS = PERCENTB + BBW, PERCENTILE, BETA); FRACTAL and ZIGZAG (they mark a pivot only after later
bars: lookahead by construction); talib.VWAP and talib.ICHIMOKU (replaced by a rolling 20-bar VWAP and an explicitly
shifted cloud, so the alignment is certain). A function missing from the installed TA-Lib is skipped and listed.
"""
import math

import numpy as np
import pandas as pd

WARM = 250          # bars at the start of each timeframe that are NA for every reading


def _sh(x, n):
    return np.r_[np.full(n, np.nan), x[:-n]]


def rmean(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def rstd(x, n):
    return pd.Series(x).rolling(n, min_periods=n).std().to_numpy()


def _runs(x: np.ndarray) -> np.ndarray:
    """Length of the current run of ones ending at each bar."""
    cs = np.cumsum(x)
    reset = np.where(x == 0, cs, 0)
    return cs - np.maximum.accumulate(reset)


def _state(a, b):
    """1 where a is above b, 0 where it is below, -1 where unknown. A tie (to rounding error) keeps the last side, so
    float noise between two equal lines cannot fire a cross."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    with np.errstate(invalid='ignore'):
        d = a - b
        s = np.where(ok & (np.abs(d) > 1e-9 * np.maximum(np.abs(a), np.abs(b))), np.sign(d), np.nan)
    side = pd.Series(s).ffill().to_numpy()
    return np.where(ok & np.isfinite(side), side > 0, -1).astype(np.int8)


def sign_codes(x) -> np.ndarray:
    """Above / below zero as a state (1 / 0, -1 unknown); an exact zero keeps the last side."""
    x = np.asarray(x, float)
    with np.errstate(invalid='ignore'):
        s = np.where(np.abs(x) > 1e-7, np.sign(x), np.nan)
    side = pd.Series(s).ffill().to_numpy()
    return np.where(np.isfinite(x) & np.isfinite(side), side > 0, -1).astype(np.int8)


PRESENT_ONLY = {'DOJI', 'LONGLEGGEDDOJI', 'RICKSHAWMAN', 'GRAVESTONEDOJI', 'DRAGONFLYDOJI', 'TAKURI'}   # +100 = present, not a direction


EXCLUDED = ['ROCP', 'ROCR', 'ROCR100', 'MACDEXT', 'MACDFIX', 'MA', 'MAVP', 'SAREXT', 'VAR', 'KSTEXT', 'LINEARREG_ANGLE',
            'LINEARREG_INTERCEPT', 'PLUS_DM', 'MINUS_DM', 'BBANDS', 'PERCENTILE', 'BETA', 'FRACTAL', 'ZIGZAG', 'VWAP',
            'ICHIMOKU', 'ATR', 'Math Operators', 'Math Transform']


def vocabulary(b: dict):
    """Returns (values, cats, missing). values: [(name, type, zero, float32 array)] normalised by type (see val);
    cats: [(name, codes int8, levels, every)]; missing: TA-Lib functions not in this install."""
    import talib as T
    o, h, l, c, v, tb = b['o'], b['h'], b['l'], b['c'], b['v'], b['tb']
    n = len(c)
    vv = np.maximum(v, 1e-12)
    V, C, missing = [], [], []

    with np.errstate(all='ignore'):
        atr, natr = T.ATR(h, l, c, 14), T.NATR(h, l, c, 14)
        vma = rmean(v, 20)
    hs_, ls_ = pd.Series(h), pd.Series(l)
    flat14 = (hs_.rolling(14, min_periods=1).max() - ls_.rolling(14, min_periods=1).min()).to_numpy() <= 0
    warm = (np.arange(n) < WARM) | flat14       # no reading at the start, or where the last 14 bars had no range at all

    def val(name, typ, fn, zero=None):
        """Compute one series, normalise it by its type and keep it as float32 (the raw float64 is dropped at once)."""
        try:
            x = np.asarray(fn(), float)
        except AttributeError:
            missing.append(name)
            return
        if typ == 'atr':
            x = x / atr
        elif typ == 'dist':
            x = (c - x) / atr
        elif typ == 'pct':
            x = x / natr
        elif typ == 'cum':
            d = x - _sh(x, 10)
            x = d / rstd(d, 200)
        elif typ == 'z':
            x = (x - rmean(x, 500)) / rstd(x, 500)
        elif typ == 'regime':
            x = x / rmean(x, 200)
        elif typ == 'vol':
            x = x / vma
        x = np.where(np.isfinite(x) & ~warm, x, np.nan).astype(np.float32)
        V.append((name, typ, (typ in ('atr', 'dist', 'pct', 'cum', 'z', 'vol')) if zero is None else zero, x))

    def cat(name, fn, levels, every=False):
        try:
            x = fn()
        except AttributeError:
            missing.append(name)
            return
        C.append((name, np.asarray(x).astype(np.int8), levels, every))

    def multi(fname, fn):
        """Call a multi-output function once; returns a tuple of arrays or None when missing."""
        try:
            return fn()
        except AttributeError:
            missing.append(fname)
            return None

    with np.errstate(all='ignore'):
        # ------------------------------------------------------------------------------------------------ momentum
        val('AC', 'atr', lambda: T.AC(h, l, 5, 34, 5))
        for p in (7, 14, 28):
            val(f'ADX{p}', 'osc', lambda p=p: T.ADX(h, l, c, p))
        val('ADXR14', 'osc', lambda: T.ADXR(h, l, c, 14))
        val('AO', 'atr', lambda: T.AO(h, l, 5, 34))
        val('APO12/26', 'atr', lambda: T.APO(c, 12, 26, 1))
        for p in (14, 25):
            r = multi('AROON', lambda p=p: T.AROON(h, l, p))
            if r is not None:
                val(f'AROONdn{p}', 'osc', lambda r=r: r[0])
                val(f'AROONup{p}', 'osc', lambda r=r: r[1])
            val(f'AROONOSC{p}', 'osc', lambda p=p: T.AROONOSC(h, l, p), zero=True)
        val('ASI', 'cum', lambda: T.ASI(o, h, l, c, 3.0))
        val('BOP', 'osc', lambda: T.BOP(o, h, l, c), zero=True)
        for p in (14, 20, 50):
            val(f'CCI{p}', 'osc', lambda p=p: T.CCI(h, l, c, p), zero=True)
        val('CG10', 'osc', lambda: T.CG(c, 10))
        val('CHOP14', 'osc', lambda: T.CHOP(h, l, c, 14))
        val('CHOPTR14', 'osc', lambda: T.CHOPTR(h, l, c, 14))
        val('CMO14', 'osc', lambda: T.CMO(c, 14), zero=True)
        val('CMOU14', 'osc', lambda: T.CMOU(c, 14), zero=True)
        val('COPPOCK', 'pct', lambda: T.COPPOCK(c, 10, 11, 14))
        val('CRSI', 'osc', lambda: T.CRSI(c, 3, 2, 100))
        val('CTI20', 'osc', lambda: T.CTI(c, 20), zero=True)
        val('DOSC', 'osc', lambda: T.DOSC(c, 14, 5, 3, 9), zero=True)
        val('DPO20', 'atr', lambda: T.DPO(c, 20))
        val('DX14', 'osc', lambda: T.DX(h, l, c, 14))
        val('ER10', 'osc', lambda: T.ER(c, 10))
        r = multi('ERI', lambda: T.ERI(h, l, c, 13))
        if r is not None:
            val('ERIbull13', 'atr', lambda: r[0])
            val('ERIbear13', 'atr', lambda: r[1])
        r = multi('FISHER', lambda: T.FISHER(h, l, 10))
        if r is not None:
            val('FISHER10', 'osc', lambda: r[0], zero=True)
            cat('FISHER>trig', lambda: _state(r[0], r[1]), ['below', 'above'])
        val('FOSC5', 'pct', lambda: T.FOSC(c, 5))
        val('IBS', 'osc', lambda: T.IBS(h, l, c))
        val('IMI14', 'osc', lambda: T.IMI(o, c, 14))
        r = multi('KDJ', lambda: T.KDJ(h, l, c))
        if r is not None:
            val('KDJ_J', 'osc', lambda: r[2])
            cat('KDJ K>D', lambda: _state(r[0], r[1]), ['below', 'above'])
        r = multi('KST', lambda: T.KST(c))
        if r is not None:
            val('KST', 'pct', lambda: r[0])
            cat('KST>sig', lambda: _state(r[0], r[1]), ['below', 'above'])
        for fa, sl, sg in ((12, 26, 9), (5, 35, 5)):
            r = multi('MACD', lambda fa=fa, sl=sl, sg=sg: T.MACD(c, fa, sl, sg))
            if r is not None:
                val(f'MACD{fa}/{sl}', 'atr', lambda r=r: r[0])
                val(f'MACDh{fa}/{sl}/{sg}', 'atr', lambda r=r: r[2])
        val('MFI14', 'osc', lambda: T.MFI(h, l, c, vv, 14))
        pdi, mdi = T.PLUS_DI(h, l, c, 14), T.MINUS_DI(h, l, c, 14)
        val('PDI14', 'osc', lambda: pdi)
        val('MDI14', 'osc', lambda: mdi)
        val('DIdiff14', 'osc', lambda: pdi - mdi, zero=True)
        val('MOM10', 'atr', lambda: T.MOM(c, 10))
        val('PPO12/26', 'pct', lambda: T.PPO(c, 12, 26, 1))
        val('PSO', 'osc', lambda: T.PSO(h, l, c, 8, 5), zero=True)
        val('QSTICK10', 'atr', lambda: T.QSTICK(o, c, 10))
        val('ROC10', 'pct', lambda: T.ROC(c, 10))
        for p in (2, 7, 14, 21):
            val(f'RSI{p}', 'osc', lambda p=p: T.RSI(c, p))
        val('SI', 'z', lambda: T.SI(o, h, l, c, 3.0))
        r = multi('SMI', lambda: T.SMI(h, l, c))
        if r is not None:
            val('SMI', 'osc', lambda: r[0], zero=True)
            cat('SMI>sig', lambda: _state(r[0], r[1]), ['below', 'above'])
        r = multi('SQZMOM', lambda: T.SQZMOM(h, l, c))
        if r is not None:
            val('SQZMOM', 'atr', lambda: r[0])
        val('STC', 'osc', lambda: T.STC(c, 23, 50, 10))
        for fk in (14, 5):
            r = multi('STOCH', lambda fk=fk: T.STOCH(h, l, c, fk, 3, 0, 3, 0))
            if r is not None:
                val(f'STOCHK{fk}', 'osc', lambda r=r: r[0])
                cat(f'STOCH{fk} K>D', lambda r=r: _state(r[0], r[1]), ['below', 'above'])
        r = multi('STOCHF', lambda: T.STOCHF(h, l, c, 5, 3, 0))
        if r is not None:
            val('STOCHFK5', 'osc', lambda: r[0])
        r = multi('STOCHRSI', lambda: T.STOCHRSI(c, 14, 14, 3, 0))
        if r is not None:
            val('STOCHRSI14', 'osc', lambda: r[0])
        for p in (15, 30):
            val(f'TRIX{p}', 'pct', lambda p=p: T.TRIX(c, p))
        val('TSI', 'osc', lambda: T.TSI(c, 25, 13), zero=True)
        val('ULTOSC', 'osc', lambda: T.ULTOSC(h, l, c, 7, 14, 28))
        val('VHF28', 'osc', lambda: T.VHF(c, 28))
        r = multi('VORTEX', lambda: T.VORTEX(h, l, c, 14))
        if r is not None:
            val('VORTEXdiff14', 'osc', lambda: r[0] - r[1], zero=True)
        val('WAD', 'cum', lambda: T.WAD(h, l, c))
        r = multi('WAVETREND', lambda: T.WAVETREND(h, l, c))
        if r is not None:
            val('WT1', 'osc', lambda: r[0], zero=True)
            cat('WT1>WT2', lambda: _state(r[0], r[1]), ['below', 'above'])
        val('WILLR14', 'osc', lambda: T.WILLR(h, l, c, 14))

        # ------------------------------------------------------------------------------------------------- overlap
        for name, fn in [('ALMA9', lambda: T.ALMA(c, 9)), ('DEMA21', lambda: T.DEMA(c, 21)), ('EMA9', lambda: T.EMA(c, 9)),
                         ('EMA21', lambda: T.EMA(c, 21)), ('EMA50', lambda: T.EMA(c, 50)), ('EMA200', lambda: T.EMA(c, 200)),
                         ('FRAMA16', lambda: T.FRAMA(h, l, 16)), ('HMA20', lambda: T.HMA(c, 20)),
                         ('HT_TRENDLINE', lambda: T.HT_TRENDLINE(c)), ('KAMA30', lambda: T.KAMA(c, 30)),
                         ('MCGD14', lambda: T.MCGD(c, 14)), ('MIDPOINT14', lambda: T.MIDPOINT(c, 14)),
                         ('MIDPRICE14', lambda: T.MIDPRICE(h, l, 14)), ('RMA14', lambda: T.RMA(c, 14)),
                         ('SMA20', lambda: T.SMA(c, 20)), ('SMA50', lambda: T.SMA(c, 50)), ('SMA200', lambda: T.SMA(c, 200)),
                         ('SWAK_BUTTER20', lambda: T.SWAK_BUTTER(c, 20)), ('SWAK_GAUSS20', lambda: T.SWAK_GAUSS(c, 20)),
                         ('T3_5', lambda: T.T3(c, 5, 0.7)), ('TEMA21', lambda: T.TEMA(c, 21)), ('TRIMA20', lambda: T.TRIMA(c, 20)),
                         ('VIDYA12', lambda: T.VIDYA(c, 12, 9)), ('VWMA20', lambda: T.VWMA(c, vv, 20)),
                         ('WMA20', lambda: T.WMA(c, 20)), ('ZLEMA21', lambda: T.ZLEMA(c, 21)),
                         ('SAR', lambda: T.SAR(h, l, 0.02, 0.2)), ('LINEARREG14', lambda: T.LINEARREG(c, 14)),
                         ('TSF14', lambda: T.TSF(c, 14)), ('MEDIAN30', lambda: T.MEDIAN(c, 30)),
                         ('AVGPRICE', lambda: T.AVGPRICE(o, h, l, c)), ('MEDPRICE', lambda: T.MEDPRICE(h, l)),
                         ('TYPPRICE', lambda: T.TYPPRICE(h, l, c)), ('WCLPRICE', lambda: T.WCLPRICE(h, l, c))]:
            val('C-' + name, 'dist', fn)
        r = multi('SUPERTREND', lambda: T.SUPERTREND(h, l, c, 10, 3.0))
        if r is not None:
            val('C-SUPERTREND10/3', 'dist', lambda: r[0])
        r = multi('MAMA', lambda: T.MAMA(c, 0.5, 0.05))
        if r is not None:
            val('C-MAMA', 'dist', lambda: r[0])
            cat('MAMA>FAMA', lambda: _state(r[0], r[1]), ['below', 'above'])
        r = multi('CKSP', lambda: T.CKSP(h, l, c, 10, 1.0, 9))
        if r is not None:
            val('C-CKSPmid', 'dist', lambda: (r[0] + r[1]) / 2)
        tp = (h + l + c) / 3
        val('C-VWAP20', 'dist', lambda: pd.Series(tp * v).rolling(20).sum().to_numpy() / pd.Series(v).rolling(20).sum().to_numpy())

        def band_pos(r):
            return (c - r[2]) / (r[0] - r[2])
        for name, fn in [('ACCBANDS20', lambda: T.ACCBANDS(h, l, c, 20)), ('KC20', lambda: T.KC(h, l, c, 20, 10, 2.0))]:
            r = multi(name, fn)
            if r is not None:
                val(name + 'pos', 'osc', lambda r=r: band_pos(r))
        for p in (20, 55):      # channel of the PREVIOUS p bars (explicit shift): a break shows as < 0 or > 1
            hi = pd.Series(h).shift(1).rolling(p, min_periods=p).max().to_numpy()
            lo = pd.Series(l).shift(1).rolling(p, min_periods=p).min().to_numpy()
            val(f'DONCHIAN{p}pos', 'osc', lambda hi=hi, lo=lo: (c - lo) / (hi - lo))
        for dev in (2.0, 2.5):
            val(f'PERCENTB20/{dev:g}', 'osc', lambda dev=dev: T.PERCENTB(c, 20, dev, dev, 0))
        e9, e21, e50, e200 = T.EMA(c, 9), T.EMA(c, 21), T.EMA(c, 50), T.EMA(c, 200)
        cat('EMA9>EMA21', lambda: _state(e9, e21), ['below', 'above'])
        cat('EMA50>EMA200', lambda: _state(e50, e200), ['below', 'above'])
        hs, ls = pd.Series(h), pd.Series(l)
        tenkan = ((hs.rolling(9).max() + ls.rolling(9).min()) / 2).to_numpy()
        kijun = ((hs.rolling(26).max() + ls.rolling(26).min()) / 2).to_numpy()
        spa = pd.Series((tenkan + kijun) / 2).shift(26).to_numpy()
        spb = (((hs.rolling(52).max() + ls.rolling(52).min()) / 2).shift(26)).to_numpy()
        top, bot = np.maximum(spa, spb), np.minimum(spa, spb)        # NaN until both spans exist
        cat('Ichimoku', lambda: np.where(np.isfinite(top) & np.isfinite(bot), np.where(c > top, 2, np.where(c < bot, 0, 1)), -1),
            ['below cloud', 'in cloud', 'above cloud'])
        cat('Tenkan>Kijun', lambda: _state(tenkan, kijun), ['below', 'above'])

        # -------------------------------------------------------------------------------------------------- volume
        val('AD', 'cum', lambda: T.AD(h, l, c, vv))
        val('ADOSC', 'vol', lambda: T.ADOSC(h, l, c, vv, 3, 10))
        val('CMF20', 'osc', lambda: T.CMF(h, l, c, vv, 20), zero=True)
        val('EFI13', 'z', lambda: T.EFI(c, vv, 13))
        val('EMV14', 'z', lambda: T.EMV(h, l, vv, 14, 10000.0))
        r = multi('KVO', lambda: T.KVO(h, l, c, vv, 34, 55, 13))
        if r is not None:
            val('KVO', 'z', lambda: r[0])
            cat('KVO>sig', lambda: _state(r[0], r[1]), ['below', 'above'])
        val('MARKETFI', 'z', lambda: T.MARKETFI(h, l, vv))
        val('NVI', 'cum', lambda: T.NVI(c, vv))
        val('OBV', 'cum', lambda: T.OBV(c, vv))
        val('PVI', 'cum', lambda: T.PVI(c, vv))
        val('PVO12/26', 'osc', lambda: T.PVO(vv, 12, 26, 1), zero=True)
        val('PVT', 'cum', lambda: T.PVT(c, vv))
        val('RVOL20', 'osc', lambda: T.RVOL(vv, 20))
        if tb is not None:
            val('TakerBuy', 'osc', lambda: np.where(v > 0, tb / np.where(v > 0, v, 1), np.nan))
        obv = T.OBV(c, vv)
        dp, do = c - _sh(c, 10), obv - _sh(obv, 10)
        cat('OBVdiv10', lambda: np.where(np.isfinite(dp) & np.isfinite(do), np.where((dp < 0) & (do > 0), 1, np.where((dp > 0) & (do < 0), 2, 0)), -1),
            ['none', 'bull div', 'bear div'])

        # ---------------------------------------------------------------------------------------------- volatility
        val('ADR14', 'regime', lambda: T.ADR(h, l, 14) / c)
        val('NATR14', 'regime', lambda: T.NATR(h, l, c, 14))
        val('BBW20', 'regime', lambda: T.BBW(c, 20, 2.0, 2.0, 0))
        val('CVI10', 'osc', lambda: T.CVI(h, l, 10, 10), zero=True)
        val('MASSI', 'osc', lambda: T.MASSI(h, l, 9, 25))
        val('ROGERSSATCHELL10', 'regime', lambda: T.ROGERSSATCHELL(o, h, l, c, 10, 252.0))
        val('RVI14', 'osc', lambda: T.RVI(c, 14, 10))
        val('RVIR14', 'osc', lambda: T.RVIR(h, l, 14, 10))
        val('TRANGE', 'atr', lambda: T.TRANGE(h, l, c), zero=False)
        val('STDDEV20', 'regime', lambda: T.STDDEV(c, 20, 1.0) / c)
        val('AVGDEV14', 'regime', lambda: T.AVGDEV(c, 14) / c)

        # --------------------------------------------------------------------------------------------------- cycle
        val('HT_DCPERIOD', 'osc', lambda: T.HT_DCPERIOD(c))
        val('HT_DCPHASE', 'osc', lambda: T.HT_DCPHASE(c))
        r = multi('HT_PHASOR', lambda: T.HT_PHASOR(c))
        if r is not None:
            val('HT_INPHASE', 'atr', lambda: r[0])
            val('HT_QUADRATURE', 'atr', lambda: r[1])
        r = multi('HT_SINE', lambda: T.HT_SINE(c))
        if r is not None:
            val('HT_SINE', 'osc', lambda: r[0], zero=True)
            cat('SINE>LEAD', lambda: _state(r[0], r[1]), ['below', 'above'])
        cat('HT_TRENDMODE', lambda: T.HT_TRENDMODE(c), ['cycle', 'trend'])
        for nm in ('SWAK_2PHP', 'SWAK_BP', 'SWAK_HP'):
            val(nm + '20', 'atr', lambda nm=nm: getattr(T, nm)(c, 20))

        # ---------------------------------------------------------------------------------- statistics, price action
        val('CORRELcv30', 'osc', lambda: T.CORREL(c, vv, 30), zero=True)
        val('KURTOSIS30', 'osc', lambda: T.KURTOSIS(c, 30))
        val('LRSLOPE14', 'atr', lambda: T.LINEARREG_SLOPE(c, 14))
        val('PERCENTRANK100', 'osc', lambda: T.PERCENTRANK(c, 100))
        val('ZSCORE20', 'osc', lambda: (c - T.SMA(c, 20)) / T.STDDEV(c, 20, 1.0), zero=True)
        r = multi('HA', lambda: T.HA(o, h, l, c))
        if r is not None:
            val('HAbody', 'atr', lambda: r[3] - r[0])
        val('BarBody', 'atr', lambda: c - o)
        run_up, run_dn = _runs((c > o).astype(np.int64)), _runs((c < o).astype(np.int64))
        cat('Runs', lambda: np.select([run_dn >= 5, run_dn >= 3, run_up >= 5, run_up >= 3], [2, 1, 4, 3], 0),
            ['none', '3-4 down', '5+ down', '3-4 up', '5+ up'])

        # ------------------------------------------------------------------------------------------------ patterns
        dead = (h == l) | (v <= 0)      # no trade, or every trade at one price: no candlestick pattern can complete
        for fn in sorted(T.get_function_groups()['Pattern Recognition']):
            x = getattr(T, fn)(o, h, l, c)
            nm = fn[3:]
            if nm in ('HIKKAKE', 'HIKKAKEMOD'):         # +/-200 marks the confirmation bar: its own event
                code = np.select([x == 100, x == -100, x == 200, x == -200], [1, 2, 3, 4], 0)
                lv = ['none', 'bull', 'bear', 'bull confirmed', 'bear confirmed']
            else:
                code = np.where(x > 0, 1, np.where(x < 0, 2, 0))
                lv = ['none', 'fires', 'fires-'] if nm in PRESENT_ONLY else ['none', 'bull', 'bear']
            C.append(('CDL:' + nm, np.where(dead, 0, code).astype(np.int8), lv, True))

        cats = []
        for name, codes, levels, every in C:
            codes = codes.copy()
            codes[warm] = -1
            cats.append((name, codes, levels, every))
    return V, cats, sorted(set(missing))
