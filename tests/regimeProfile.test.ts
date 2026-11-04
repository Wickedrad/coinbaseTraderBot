import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { parseProfile, regimeConfig, regimeStrategy, volRegime } from '../bot/strategy/regimeProfile';

const env = { DASHBOARD_TOKEN: 'x'.repeat(32) };

test('volatility regimes: off without VOLREG_RV1H (the same config object comes back)', () => {
  const cfg = loadConfig({ ...env, VOLREG_CALM: 'VOL_FALLBACK_MULT=1' });
  assert.equal(cfg.strategy.volRegime, undefined);
  assert.equal(regimeStrategy(cfg.strategy, 1e-5), cfg.strategy);
  assert.equal(regimeConfig(cfg, 1e-5), cfg);
});

test('volatility regimes: calm / normal / wild pick their own validated settings', () => {
  const cfg = loadConfig({ ...env, VOL_FALLBACK_MULT: '1.15', VOLREG_RV1H: '0.00009,0.0002',
    VOLREG_CALM: 'VOL_FALLBACK_MULT=1.0+STRATEGY_KAPPA=0.75', VOLREG_WILD: 'VOL_FALLBACK_MULT=1.3+HOURLY_MID_BAND=0.2,0.8' });
  const S = cfg.strategy;
  assert.deepEqual(S.volRegime?.rv1h, [0.00009, 0.0002]);
  assert.equal(volRegime(5e-5, S.volRegime!.rv1h), 'calm');
  assert.equal(volRegime(1e-4, S.volRegime!.rv1h), 'normal');
  assert.equal(volRegime(3e-4, S.volRegime!.rv1h), 'wild');
  assert.equal(volRegime(null, S.volRegime!.rv1h), undefined);
  const calm = regimeStrategy(S, 5e-5);
  assert.equal(calm.volFallbackMult, 1.0);
  assert.equal(calm.kappa, 0.75);
  assert.equal(calm.volRegime, undefined, 'a profile carries no profiles of its own');
  const wild = regimeStrategy(S, 3e-4);
  assert.equal(wild.volFallbackMult, 1.3);
  assert.deepEqual(wild.hourlyMidBand, [0.2, 0.8]);
  assert.equal(wild.kappa, S.kappa);
  // No VOLREG_NORMAL: the normal regime keeps the bot's own settings; no reading yet: the bot's own.
  assert.equal(regimeStrategy(S, 1e-4), S);
  assert.equal(regimeStrategy(S, undefined), S);
  const c = regimeConfig(cfg, 5e-5);
  assert.notEqual(c, cfg);
  assert.equal(c.strategy, calm);
  assert.equal(c.risk, cfg.risk);
});

test('volatility regimes: bad profiles are refused like bad settings', () => {
  assert.throws(() => loadConfig({ ...env, VOLREG_RV1H: '0.0002,0.0001', VOLREG_CALM: 'VOL_FALLBACK_MULT=1' }));
  assert.throws(() => loadConfig({ ...env, VOLREG_RV1H: '0.0001,0.0002', VOLREG_CALM: 'VOL_FALLBACK_MULT=9' }));
  assert.throws(() => loadConfig({ ...env, VOLREG_RV1H: '0.0001,0.0002', VOLREG_CALM: 'vol=1' }));
  assert.throws(() => loadConfig({ ...env, VOLREG_RV1H: '0.0001,0.0002', VOLREG_CALM: 'VOLREG_RV1H=1,2' }));
  assert.deepEqual(parseProfile('A=1+B_C=0.2,0.8', 'K'), { A: '1', B_C: '0.2,0.8' });
  assert.equal(parseProfile('  ', 'K'), undefined);
});
