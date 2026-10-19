import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../data-access/synthetic-data';
import { DEFAULT_FILTERS, arsenalByType, filterPitches, headDescription, mean, metric, pitchMetrics, predictionWarnings, productText } from './pitch-analysis';

describe('Análisis de pitcheo', () => {
  const bundle = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);

  it('combina los cuatro filtros sin incluir otras temporadas o categorías', () => {
    const pitch = bundle.pitches[0];
    const filtered = filterPitches(bundle.pitches, {
      pitcherId: pitch.pitcherId, season: pitch.season,
      category: pitch.category, pitchType: pitch.pitchType,
    });
    expect(filtered.length).toBeGreaterThan(0);
    expect(filtered.every((p) => p.pitcherId === pitch.pitcherId && p.season === pitch.season &&
      p.category === pitch.category && p.pitchType === pitch.pitchType)).toBeTrue();
    expect(filterPitches(bundle.pitches, DEFAULT_FILTERS).length).toBe(bundle.pitches.length);
  });

  it('no convierte valores ausentes en cero ni promedios', () => {
    expect(mean([null, undefined, NaN])).toBeNull();
    expect(mean([100, null, 120])).toBe(110);
    expect(metric(null)).toBe('\u2014');
    expect(pitchMetrics([]).stuff).toBeNull();
  });

  it('pondera uso y medias del arsenal por número de pitches', () => {
    const row = bundle.arsenal[0];
    const arsenal = arsenalByType([
      { ...row, n: 10, stuffPlus: 80 },
      { ...row, n: 30, stuffPlus: 120 },
    ]);
    expect(arsenal[0].stuff).toBe(110);
    expect(arsenal[0].usage).toBe(100);
    expect(arsenalByType([{ ...row, stuffPlus: null }])[0].stuff).toBeNull();
  });

  it('traduce nombres internos de modelos en textos recibidos del backend', () => {
    const copy = productText('F8 provisional; F10 experimental; F9 contextual.');
    expect(copy).not.toMatch(/\bF(?:8|9|10)\b/i);
    expect(copy).toContain('simulador de altitud');
  });

  it('explica advertencias y prevalencias sin exponer códigos técnicos', () => {
    const warnings = predictionWarnings('unseen_pitcher_base_policy_requires_no_history;diagnostic_stuff_model;outside_training_range:spin_rate');
    expect(warnings).not.toContain('_');
    expect(warnings).toContain('Lanzador sin historial');
    expect(headDescription('smoothed_training_prevalence', 'experimental')).toContain('no es una predicción individual');
  });
});
