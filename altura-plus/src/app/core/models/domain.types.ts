export type AltitudeCategory = 'Extreme' | 'Medium' | 'No Altitude';
export const ALTITUDE_CATEGORIES: readonly AltitudeCategory[] = ['Extreme', 'Medium', 'No Altitude'];
export const ALTITUDE_LABELS: Record<AltitudeCategory, string> = {
  Extreme: 'Altitud extrema',
  Medium: 'Altitud media',
  'No Altitude': 'Sin altitud',
};

export type PitchType = 'FB' | 'CT' | 'SI' | 'SL' | 'CB' | 'CH' | 'SP' | 'SW';
export const PITCH_TYPES: readonly PitchType[] = ['FB', 'CT', 'SI', 'SL', 'CB', 'CH', 'SP', 'SW'];

export const PITCH_TYPE_NAMES: Record<PitchType, string> = {
  FB: 'Recta de cuatro costuras',
  CT: 'Cúter',
  SI: 'Sínker',
  SL: 'Slider',
  CB: 'Curva',
  CH: 'Cambio de velocidad',
  SP: 'Splitter',
  SW: 'Sweeper',
};

export type EvidenceRegime = 'interpolado' | 'extrapolado' | 'insuficiente';
export type RouteMode = 'A' | 'B';

/**
 * Bandas interpretativas de la escala plus (100 + 10·z), espejo de
 * `scale_bands` en GET /api/v1/models. Referencia fija 2025 ajustada por
 * temporada, NO por estadio (sin stadium_id) — etiqueta orientativa.
 */
export interface ScaleBand { label: string; detail: string }
export function bandFor(score: number): ScaleBand {
  if (score >= 120) return { label: 'elite', detail: '~percentil 97' };
  if (score >= 110) return { label: 'sobre promedio', detail: '+1 DE' };
  if (score >= 90) return { label: 'promedio', detail: '±1 DE de la media' };
  if (score >= 80) return { label: 'bajo promedio', detail: '−1 DE' };
  return { label: 'por debajo de reemplazo', detail: '≥2 DE peor' };
}

export interface Pitcher {
  id: string;
  label: string;
  throws: 'R' | 'L';
}

export interface ScoreSummary {
  value: number;
  ci: readonly [number, number];
  n: number;
  regime: EvidenceRegime;
  modelAvailable: boolean;
  max: number;
  avg: number;
}

export interface PitchScore {
  id: string;
  pitcherId: string;
  pitchType: PitchType;
  season: number;
  /** 'test_2026' = partición sellada: score F8 inferido, sin calibración F9. */
  partition?: 'phase_review' | 'test_2026';
  category: AltitudeCategory;
  veloMph: number;
  spinRpm: number;
  ivbIn: number;
  hbIn: number;
  plateXIn: number;
  plateZIn: number;
  /** Contexto del conteo/lado: necesario para evaluar con la familia combinada
   * `pitching` (no solo con `stuff`). Ausente en datos sintéticos. */
  balls?: number | null;
  strikes?: number | null;
  batterSide?: 'L' | 'R' | null;
  extensionFt?: number | null;
  releaseHeightFt?: number | null;
  releaseSideFt?: number | null;
  spinAxisSin?: number;
  spinAxisCos?: number;
  apiPitchType?: string;
  stuffPlus: number | null;
  locationPlus: number | null;
  pitchingPlus: number | null;
  /** F11 experimental: physical + location + historical arsenal + observed context. */
  stuffFinal?: number | null;
  finalHistoryN?: number | null;
  finalHistoryStatus?: 'regularized_2024_history' | 'group_prior_only' | null;
}

export interface ArsenalRow {
  pitcherId: string;
  pitchType: PitchType;
  season: number;
  category: AltitudeCategory;
  n: number;
  usagePct: number;
  veloMphAvg: number;
  spinRpmAvg: number;
  ivbInAvg: number;
  hbInAvg: number;
  /** Medias físicas del pitcher (defaults del simulador); ausentes en modo sintético. */
  spinAxisSinAvg?: number;
  spinAxisCosAvg?: number;
  relHeightAvg?: number;
  relSideAvg?: number;
  extensionAvg?: number;
  stuffPlus: number | null;
  stuffCi: readonly [number, number] | null;
}

export interface ScenarioDelta {
  pitcherId: string;
  pitchType: PitchType;
  scenarioA: AltitudeCategory;
  scenarioB: AltitudeCategory;
  /** null = sin estimación (soporte insuficiente); nunca se fabrica un 0. */
  deltaStuffPlus: number | null;
  ci: readonly [number, number] | null;
  nA: number;
  nB: number;
  regime: EvidenceRegime;
}

export interface PitcherBundle {
  pitcher: Pitcher;
  stuffPlus: ScoreSummary;
  locationPlus: ScoreSummary;
  pitchingPlus: ScoreSummary;
  spin: { avgRpm: number; maxRpm: number; axisDeg: number };
  arsenal: ArsenalRow[];
  pitches: PitchScore[];
  deltas: ScenarioDelta[];
}

export interface SimulatorExample {
  label: string;
  pitchType: PitchType;
  veloMph: number;
  spinRpm: number;
  ivbIn: number;
  hbIn: number;
  plateXIn: number;
  plateZIn: number;
}
