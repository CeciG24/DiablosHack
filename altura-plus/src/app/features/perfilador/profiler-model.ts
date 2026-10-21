import { ALTITUDE_TO_API } from '../simulador/simulator-candidates';
import { PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import { ALTITUDE_CATEGORIES, PITCH_TYPES, PitcherBundle, PitchScore } from '../../core/models/domain.types';
import { Candidate, CandidateRow, PhysicalKey, ProfilerPayload } from '../../core/models/profiler.types';

export const PHYSICAL_FIELDS: { key: PhysicalKey; label: string; unit: string; min: number; max: number; step: number }[] = [
  { key: 'veloMph', label: 'Velocidad', unit: 'mph', min: 30, max: 110, step: .1 },
  { key: 'spinRpm', label: 'Spin', unit: 'rpm', min: 0, max: 5000, step: 1 },
  { key: 'ivbIn', label: 'IVB', unit: 'in', min: -40, max: 40, step: .1 },
  { key: 'hbIn', label: 'HB', unit: 'in', min: -40, max: 40, step: .1 },
  { key: 'extensionFt', label: 'Extensión', unit: 'ft', min: 0, max: 10, step: .01 },
  { key: 'releaseHeightFt', label: 'Altura de liberación', unit: 'ft', min: 0, max: 10, step: .01 },
  { key: 'releaseSideFt', label: 'Liberación lateral', unit: 'ft', min: -8, max: 8, step: .01 },
  { key: 'axisDeg', label: 'Eje de giro', unit: 'grados', min: 0, max: 360, step: 1 },
];

export function emptyRow(): CandidateRow {
  return { key: crypto.randomUUID(), type: 'FB', category: 'No Altitude', usage: 100, n: null,
    veloMph: null, spinRpm: null, ivbIn: null, hbIn: null, extensionFt: null,
    releaseHeightFt: null, releaseSideFt: null, axisDeg: null };
}
export function emptyCandidate(): Candidate {
  return { name: 'Candidato sin nombre', hand: 'Right', mode: 'profiles', rows: [emptyRow()], provenance: 'Entrada manual' };
}
export function rowWeight(candidate: Candidate, row: CandidateRow): number {
  return candidate.mode === 'pitches' ? 1 : row.usage ?? 0;
}
export function issues(candidate: Candidate): string[] {
  const errors: string[] = [];
  if (!candidate.rows.length || candidate.rows.length > 1000) errors.push('Se requieren entre 1 y 1000 registros.');
  if (new Set(candidate.rows.map((r) => r.key)).size !== candidate.rows.length) errors.push('Hay claves de registro repetidas.');
  if (candidate.hand !== 'Right' && candidate.hand !== 'Left') errors.push('Selecciona una mano válida.');
  if (candidate.mode === 'profiles' && Math.abs(candidate.rows.reduce((n, r) => n+(r.usage ?? 0), 0)-100) > .01) errors.push('El uso del repertorio debe sumar 100%.');
  for (const [i, row] of candidate.rows.entries()) {
    if (!PITCH_TYPES.includes(row.type) || !ALTITUDE_CATEGORIES.includes(row.category)) errors.push(`Fila ${i+1}: revisa el tipo y el origen.`);
    if (candidate.mode === 'profiles' && (row.usage === null || !Number.isFinite(row.usage) || row.usage < 0 || row.usage > 100)) errors.push(`Fila ${i+1}: uso inválido.`);
    if (row.n !== null && (!Number.isInteger(row.n) || row.n < 1 || row.n > 1000000)) errors.push(`Fila ${i+1}: n debe ser un entero entre 1 y 1000000.`);
    if (rowWeight(candidate, row) === 0) continue;
    const missing = PHYSICAL_FIELDS.filter((f) => row[f.key] === null || !Number.isFinite(row[f.key]) || row[f.key]! < f.min || row[f.key]! > f.max);
    if (missing.length) errors.push(`Fila ${i+1}: completa o corrige ${missing.map((f) => f.label).join(', ')}.`);
  }
  return errors;
}
export function payloadFor(candidate: Candidate, target: CandidateRow['category']): ProfilerPayload {
  if (issues(candidate).length) throw new Error('Arsenal incompleto o inválido');
  return { mode: candidate.mode, target: ALTITUDE_TO_API[target],
    entries: candidate.rows.filter((r) => rowWeight(candidate, r) > 0).map((row) => {
      const axis = row.axisDeg! * Math.PI / 180;
      return { key: row.key, weight: rowWeight(candidate, row), observed_n: candidate.mode === 'pitches' ? 1 : row.n,
        pitch: { auto_pitch_type: PITCH_TYPE_TO_API[row.type], pitcher_throws: candidate.hand,
          altitude_category: ALTITUDE_TO_API[row.category], rel_speed: row.veloMph, spin_rate: row.spinRpm,
          induced_vert_break: row.ivbIn, horz_break: row.hbIn, extension: row.extensionFt,
          rel_height: row.releaseHeightFt, rel_side: row.releaseSideFt,
          spin_axis_sin: Math.sin(axis), spin_axis_cos: Math.cos(axis) } };
    }) };
}
export function weightedValue(candidate: Candidate, rows: CandidateRow[], key: PhysicalKey): number | null {
  const valid = rows.filter((r) => r[key] !== null && Number.isFinite(r[key]) && rowWeight(candidate, r) > 0);
  const total = valid.reduce((n, r) => n + rowWeight(candidate, r), 0);
  return total ? valid.reduce((n, r) => n + r[key]!*rowWeight(candidate, r), 0)/total : null;
}
export function shapeGroups(candidate: Candidate): CandidateRow[] {
  const groups = new Map<string, CandidateRow[]>();
  for (const row of candidate.rows) {
    const key = `${row.type}|${row.category}`;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const total = candidate.rows.reduce((n, r) => n + rowWeight(candidate, r), 0);
  return [...groups].map(([key, rows]) => {
    const values = Object.fromEntries(PHYSICAL_FIELDS.map((f) => [f.key, weightedValue(candidate, rows, f.key)]));
    const axes = rows.filter((r) => r.axisDeg !== null && rowWeight(candidate, r) > 0);
    const sin = axes.reduce((n, r) => n+Math.sin(r.axisDeg!*Math.PI/180)*rowWeight(candidate, r), 0);
    const cos = axes.reduce((n, r) => n+Math.cos(r.axisDeg!*Math.PI/180)*rowWeight(candidate, r), 0);
    return { ...rows[0], ...values, key, axisDeg: axes.length && Math.hypot(sin, cos) > 1e-9 ? (Math.atan2(sin, cos)*180/Math.PI+360)%360 : null,
      n: rows.every((r) => r.n !== null) ? rows.reduce((n, r) => n+r.n!, 0) : null,
      usage: total ? rows.reduce((n, r) => n+rowWeight(candidate, r), 0)/total*100 : 0 } as CandidateRow;
  });
}
export function fromBundle(bundle: PitcherBundle, season: '2025' | '2026' | 'both'): Candidate {
  return { name: bundle.pitcher.label, hand: bundle.pitcher.throws === 'L' ? 'Left' : 'Right', mode: 'pitches',
    provenance: `Muestra cargada de ${bundle.pitcher.label}; no es todo el historial`,
    rows: bundle.pitches.filter((p) => season === 'both' || p.season === Number(season)).map((p) => ({
      key: p.id, type: p.pitchType, category: p.category, usage: null, n: 1, year: p.season,
      veloMph: p.veloMph, spinRpm: p.spinRpm, ivbIn: p.ivbIn, hbIn: p.hbIn,
      extensionFt: p.extensionFt ?? null, releaseHeightFt: p.releaseHeightFt ?? null, releaseSideFt: p.releaseSideFt ?? null,
      axisDeg: p.spinAxisSin == null || p.spinAxisCos == null ? null : (Math.atan2(p.spinAxisSin, p.spinAxisCos)*180/Math.PI+360)%360,
    })) };
}
export function toMapPitch(row: CandidateRow): PitchScore | null {
  if (row.hbIn === null || row.ivbIn === null) return null;
  return { id: row.key, pitcherId: '', pitchType: row.type, category: row.category, season: row.year ?? 0,
    veloMph: row.veloMph ?? 0, spinRpm: row.spinRpm ?? 0, ivbIn: row.ivbIn, hbIn: row.hbIn,
    plateXIn: 0, plateZIn: 0, stuffPlus: null, locationPlus: null, pitchingPlus: null };
}
