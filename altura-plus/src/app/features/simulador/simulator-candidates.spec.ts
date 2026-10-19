import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { arsenalCandidates } from './simulator-candidates';

describe('Candidatos del arsenal para recomendaciones', () => {
  const bundle = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);
  const base = {
    ...bundle.arsenal[0], season: 2025,
    spinAxisSinAvg: 0.3, spinAxisCosAvg: -0.4,
    relHeightAvg: 6, relSideAvg: 2, extensionAvg: 6.2,
  };

  it('normaliza el eje y envía únicamente físicas de la categoría origen', () => {
    const rows = arsenalCandidates([base, { ...base, season: 2026 }], bundle.pitcher, base.category);
    expect(rows.length).toBe(1);
    expect(rows[0].spin_axis_sin ** 2 + rows[0].spin_axis_cos ** 2).toBeCloseTo(1, 8);
    expect(rows[0].pitcher_anon_id).toBe(bundle.pitcher.id);
  });

  it('no inventa físicas para completar un candidato', () => {
    expect(arsenalCandidates([{ ...base, extensionAvg: undefined }], bundle.pitcher, base.category)).toEqual([]);
    expect(arsenalCandidates([{ ...base, spinAxisSinAvg: 0, spinAxisCosAvg: 0 }], bundle.pitcher, base.category)).toEqual([]);
  });
});
