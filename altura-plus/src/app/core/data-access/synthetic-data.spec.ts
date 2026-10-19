import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from './synthetic-data';
import { ALTITUDE_CATEGORIES } from '../models/domain.types';

describe('buildSyntheticBundle', () => {
  const bundle = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);

  it('genera datos deterministas', () => {
    const again = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);
    expect(again.stuffPlus.value).toEqual(bundle.stuffPlus.value);
    expect(again.pitches.length).toEqual(bundle.pitches.length);
  });

  it('produce arsenal en todas las categorías de altitud', () => {
    const cats = new Set(bundle.arsenal.map((r) => r.category));
    for (const c of ALTITUDE_CATEGORIES) expect(cats.has(c)).toBeTrue();
  });

  it('marca régimen insuficiente cuando la muestra es baja', () => {
    const deltas = SYNTHETIC_PITCHERS.flatMap((p) => buildSyntheticBundle(p).deltas);
    const thin = deltas.filter((d) => Math.min(d.nA, d.nB) < 40);
    expect(thin.length).toBeGreaterThan(0);
    for (const d of thin) expect(d.regime).toBe('insuficiente');
  });

  it('mantiene intervalos con lo <= hi', () => {
    for (const d of bundle.deltas) {
      expect(d.ci).not.toBeNull();
      expect(d.ci![0]).toBeLessThanOrEqual(d.ci![1]);
    }
  });
});
