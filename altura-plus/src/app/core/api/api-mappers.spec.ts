import { apiBundleToDomain, apiPitcherToDomain, PITCH_TYPE_TO_API } from './api-mappers';
import { ApiBundle } from './api.service';

const BUNDLE: ApiBundle = {
  pitcher_anon_id: 'pitcher_00461',
  throws: 'Right',
  n: 466,
  games: 12,
  spin: { avg_rpm: 2400.4, max_rpm: 2890.2, axis_deg: 181.1 },
  summaries: {
    stuff: { mean: 110.7, ci: [108.1, 113.3], n: 466 },
    location: { mean: 100.1, ci: [99.0, 101.2], n: 466 },
    pitching: { mean: 101.1, ci: [100.0, 102.2], n: 466 },
  },
  arsenal: [
    {
      auto_pitch_type: 'Four-Seam', altitude_category: 'No Altitude', n: 150, usage: 0.32,
      rel_speed: 93.1, spin_rate: 2350,
      spin_axis_sin: -0.81, spin_axis_cos: 0.59, rel_height: 5.98, rel_side: 3.2, extension: 6.15,
      induced_vert_break: 16.2, horz_break: -7.8,
      stuff_plus: 108.4, ci: [106.0, 110.8],
    },
    { auto_pitch_type: 'Other', altitude_category: 'No Altitude', n: 2, usage: 0.004,
      rel_speed: 80, spin_rate: 2000,
      spin_axis_sin: 0, spin_axis_cos: 1, rel_height: 6, rel_side: 1, extension: 6,
      induced_vert_break: 5, horz_break: 0, stuff_plus: 90, ci: [85, 95] },
  ],
  pitches: [
    {
      pitch_uid: 'u1', auto_pitch_type: 'Four-Seam', year: 2025, altitude_category: 'Extreme Altitude',
      rel_speed: 93.05, spin_rate: 2350.2,
      spin_axis_sin: -0.81, spin_axis_cos: 0.59, rel_height: 5.98, rel_side: 3.2, extension: 6.15,
      induced_vert_break: 12.6, horz_break: -6.5,
      plate_loc_height: 2.5, plate_loc_side: 0.1,
      stuff_plus: 105.3, location_plus: 99.2, pitching_plus: 97.0, experimental_score: 97.05,
    },
  ],
  deltas: [
    { auto_pitch_type: 'Four-Seam', scenario_a: 'No Altitude', scenario_b: 'Extreme Altitude',
      delta_score: -5.99, ci: [-7.75, -4.24], n_a: 90, n_b: 80, n_simulated: 7, regime: 'extrapolado' },
    { auto_pitch_type: 'Changeup', scenario_a: 'No Altitude', scenario_b: 'Extreme Altitude',
      delta_score: null, ci: null, n_a: 5, n_b: 2, n_simulated: 0, regime: 'insuficiente' },
  ],
  scope: 'test',
};

describe('api-mappers', () => {
  it('mapea pitcher_anon_id a Pitcher de dominio', () => {
    const p = apiPitcherToDomain({ pitcher_anon_id: 'pitcher_00332', throws: 'Left', n: 204, games: 3, n_categories: 2, has_2026: true, experimental_score: 110 });
    expect(p.id).toBe('pitcher_00332');
    expect(p.throws).toBe('L');
    expect(p.label).toContain('00332');
  });

  it('convierte bundle completo con mapeo de tipos y categorías', () => {
    const b = apiBundleToDomain(BUNDLE);
    expect(b.pitcher.id).toBe('pitcher_00461');
    expect(b.pitcher.throws).toBe('R');
    expect(b.stuffPlus.value).toBeCloseTo(110.7, 1);
    expect(b.stuffPlus.regime).toBe('interpolado');
    // 'Other' no mapea a PitchType → se descarta del arsenal.
    expect(b.arsenal.length).toBe(1);
    expect(b.arsenal[0].pitchType).toBe('FB');
    expect(b.arsenal[0].category).toBe('No Altitude');
    expect(b.arsenal[0].usagePct).toBeCloseTo(32, 0);
    // Pitch: Extreme Altitude → 'Extreme', ubicación pies→pulgadas.
    expect(b.pitches[0].category).toBe('Extreme');
    expect(b.pitches[0].plateZIn).toBeCloseTo(30, 0);
    expect(b.pitches[0].season).toBe(2025);
    // Delta orientado y con régimen del backend.
    const d = b.deltas.find((x) => x.pitchType === 'FB');
    expect(d?.scenarioA).toBe('No Altitude');
    expect(d?.scenarioB).toBe('Extreme');
    expect(d?.deltaStuffPlus).toBeCloseTo(-6.0, 1);
    expect(d?.regime).toBe('extrapolado');
  });

  it('PITCH_TYPE_TO_API cubre los 8 tipos del frontend', () => {
    expect(PITCH_TYPE_TO_API.FB).toBe('Four-Seam');
    expect(PITCH_TYPE_TO_API.SI).toBe('Sinker');
    expect(PITCH_TYPE_TO_API.SW).toBe('Sweeper');
  });

  it('conserva las físicas completas para evaluar el pitch sin inventar release', () => {
    const pitch = apiBundleToDomain(BUNDLE).pitches[0];
    expect(pitch.extensionFt).toBe(6.15);
    expect(pitch.releaseHeightFt).toBe(5.98);
    expect(pitch.releaseSideFt).toBe(3.2);
    expect(pitch.spinAxisSin).toBe(-0.81);
    expect(pitch.veloMph).toBe(93.05);
    expect(pitch.apiPitchType).toBe('Four-Seam');
  });

  it('no sustituye scores ni intervalos ausentes por un promedio ficticio', () => {
    const bundle = apiBundleToDomain({
      ...BUNDLE,
      pitches: [{ ...BUNDLE.pitches[0], stuff_plus: null, location_plus: null, pitching_plus: null }],
      arsenal: [{ ...BUNDLE.arsenal[0], stuff_plus: null, ci: null }],
    });
    expect(bundle.pitches[0].stuffPlus).toBeNull();
    expect(bundle.pitches[0].locationPlus).toBeNull();
    expect(bundle.pitches[0].pitchingPlus).toBeNull();
    expect(bundle.arsenal[0].stuffPlus).toBeNull();
    expect(bundle.arsenal[0].stuffCi).toBeNull();
  });
});
