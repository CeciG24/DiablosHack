import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { movementReference } from './simulator-reference';

describe('Referencia de movimiento', () => {
  const pitch = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]).pitches[0];
  it('calcula deciles en la cohorte completa y limita el render sin perder extremos', () => {
    const pitches = Array.from({ length: 1000 }, (_, i) => ({ ...pitch, id: String(i), stuffPlus: i }));
    const reference = movementReference(pitches);
    expect(reference.n).toBe(1000);
    expect(reference.sample.length).toBe(360);
    expect(reference.sample[0].stuffPlus).toBe(0);
    expect(reference.sample[359].stuffPlus).toBe(999);
    expect(reference.extremes!.best.every((i) => reference.sample[i].stuffPlus! >= 900)).toBeTrue();
    expect(reference.extremes!.worst.every((i) => reference.sample[i].stuffPlus! <= 99)).toBeTrue();
  });
  it('no fabrica deciles con pocos datos, valores ausentes o scores idénticos', () => {
    expect(movementReference([{ ...pitch, stuffPlus: null }, { ...pitch, stuffPlus: NaN }]).n).toBe(0);
    expect(movementReference([pitch]).extremes).toBeNull();
    expect(movementReference(Array(30).fill({ ...pitch, stuffPlus: 100 })).extremes).toBeNull();
  });
});
