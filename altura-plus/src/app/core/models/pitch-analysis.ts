import { AltitudeCategory, ArsenalRow, PitchScore, PitchType } from './domain.types';

export interface PitchFilters {
  pitcherId: string;
  season: number | 'ALL';
  pitchType: PitchType | 'ALL';
  category: AltitudeCategory | 'ALL';
}

export const DEFAULT_FILTERS: PitchFilters = {
  pitcherId: 'ALL', season: 'ALL', pitchType: 'ALL', category: 'ALL',
};

export function filterPitches(pitches: readonly PitchScore[], filters: PitchFilters): PitchScore[] {
  return pitches.filter((p) =>
    (filters.pitcherId === 'ALL' || p.pitcherId === filters.pitcherId) &&
    (filters.season === 'ALL' || p.season === filters.season) &&
    (filters.pitchType === 'ALL' || p.pitchType === filters.pitchType) &&
    (filters.category === 'ALL' || p.category === filters.category));
}

export function mean(values: readonly (number | null | undefined)[]): number | null {
  const valid = values.filter((v): v is number => v != null && Number.isFinite(v));
  return valid.length ? valid.reduce((sum, v) => sum + v, 0) / valid.length : null;
}

export function metric(value: number | null | undefined, decimals = 1): string {
  return value != null && Number.isFinite(value) ? value.toFixed(decimals) : '\u2014';
}

export function productText(text: string): string {
  return text.replace(/\bF10\b/gi, 'simulador de altitud')
    .replace(/\bF9\b/gi, 'modelo contextual')
    .replace(/\bF8\b/gi, 'modelo de evaluaci\u00f3n');
}

export function predictionWarnings(text: string): string {
  const messages = text.split(';').filter(Boolean).map((warning) => {
    if (warning === 'diagnostic_stuff_model') return 'Evaluación física de diagnóstico.';
    if (warning === 'unseen_pitcher_base_policy_requires_no_history') return 'Lanzador sin historial en la referencia de entrenamiento.';
    if (warning.startsWith('outside_training_range:')) return 'Hay características fuera del rango observado en entrenamiento.';
    return 'El modelo solicita revisar el soporte de esta estimación.';
  });
  return [...new Set(messages)].join(' ');
}

export function headDescription(route: string | undefined, status: string | undefined): string {
  if (route === 'smoothed_training_prevalence') return 'Prevalencia de entrenamiento suavizada; no es una predicción individual.';
  if (route === 'model') return status === 'validated' ? 'Modelo individual validado en su protocolo de evaluación.' : 'Modelo individual experimental.';
  return 'Procedencia de la estimación no informada por el backend.';
}

export function pitchMetrics(pitches: readonly PitchScore[]) {
  return {
    stuff: mean(pitches.map((p) => p.stuffPlus)),
    location: mean(pitches.map((p) => p.locationPlus)),
    pitching: mean(pitches.map((p) => p.pitchingPlus)),
  };
}

export function arsenalByType(rows: readonly ArsenalRow[]) {
  const groups = new Map<PitchType, ArsenalRow[]>();
  for (const row of rows) groups.set(row.pitchType, [...(groups.get(row.pitchType) ?? []), row]);
  const total = rows.reduce((sum, row) => sum + row.n, 0);
  return [...groups].map(([type, group]) => {
    const n = group.reduce((sum, row) => sum + row.n, 0);
    const weighted = (pick: (row: ArsenalRow) => number) =>
      group.reduce((sum, row) => sum + pick(row) * row.n, 0) / Math.max(n, 1);
    const scored = group.filter((row) => row.stuffPlus != null && Number.isFinite(row.stuffPlus));
    const scoredN = scored.reduce((sum, row) => sum + row.n, 0);
    return {
      type, n, usage: total ? n / total * 100 : 0,
      velo: weighted((r) => r.veloMphAvg),
      spin: weighted((r) => r.spinRpmAvg),
      ivb: weighted((r) => r.ivbInAvg),
      hb: weighted((r) => r.hbInAvg),
      stuff: scoredN ? scored.reduce((sum, row) => sum + (row.stuffPlus ?? 0) * row.n, 0) / scoredN : null,
    };
  }).sort((a, b) => b.n - a.n);
}
