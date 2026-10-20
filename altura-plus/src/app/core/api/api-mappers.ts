import {
  AltitudeCategory,
  ArsenalRow,
  EvidenceRegime,
  PitchScore,
  PitchType,
  Pitcher,
  PitcherBundle,
  ScenarioDelta,
  ScoreSummary,
} from '../models/domain.types';
import { ApiArsenalRow, ApiBundle, ApiDelta, ApiPitch, ApiPitcherRow } from './api.service';

/** Mapeo vocabulario del backend → tipos del frontend. */
export const PITCH_TYPE_FROM_API: Record<string, PitchType> = {
  'Four-Seam': 'FB',
  'TwoSeamFastBall': 'SI',
  'OneSeamFastBall': 'FB',
  'Sinker': 'SI',
  'Cutter': 'CT',
  'Slider': 'SL',
  'Curveball': 'CB',
  'Changeup': 'CH',
  'Splitter': 'SP',
  'Sweeper': 'SW',
};

export const ALTITUDE_FROM_API: Record<string, AltitudeCategory> = {
  'Extreme Altitude': 'Extreme',
  'Medium Altitude': 'Medium',
  'No Altitude': 'No Altitude',
};

const PITCH_TYPE_TO_API = Object.fromEntries(
  Object.entries(PITCH_TYPE_FROM_API).map(([api, fe]) => [fe, api]),
) as Record<PitchType, string>;
// Prefer canonical names: Sink→'Sinker' no 'TwoSeamFastBall'.
PITCH_TYPE_TO_API.SI = 'Sinker';
PITCH_TYPE_TO_API.FB = 'Four-Seam';
export { PITCH_TYPE_TO_API };

const round1 = (v: number) => Math.round(v * 10) / 10;

function regimeFor(n: number): EvidenceRegime {
  return n >= 120 ? 'interpolado' : n >= 40 ? 'extrapolado' : 'insuficiente';
}

function scoreSummary(mean: number | null, ci: [number, number] | null, n: number): ScoreSummary {
  const value = mean ?? 100;
  return {
    value: round1(value),
    ci: ci ? [round1(ci[0]), round1(ci[1])] : [value, value],
    n,
    regime: regimeFor(n),
    modelAvailable: mean !== null,
    max: ci ? round1(Math.max(value, ci[1])) : value,
    avg: 100,
  };
}

function mapPitch(p: ApiPitch, pitcherId: string): PitchScore | null {
  const pitchType = PITCH_TYPE_FROM_API[p.auto_pitch_type];
  const category = ALTITUDE_FROM_API[p.altitude_category];
  if (!pitchType || !category) return null;
  return {
    id: p.pitch_uid,
    pitcherId,
    pitchType,
    season: p.year,
    partition: p.partition,
    category,
    veloMph: p.rel_speed,
    spinRpm: p.spin_rate,
    ivbIn: p.induced_vert_break,
    hbIn: p.horz_break,
    plateXIn: p.plate_loc_side * 12,
    plateZIn: p.plate_loc_height * 12,
    balls: p.balls ?? null,
    strikes: p.strikes ?? null,
    batterSide: p.batter_side === 'Left' || p.batter_side === 'Right' ? (p.batter_side === 'Left' ? 'L' : 'R') : null,
    extensionFt: p.extension,
    releaseHeightFt: p.rel_height,
    releaseSideFt: p.rel_side,
    spinAxisSin: p.spin_axis_sin,
    spinAxisCos: p.spin_axis_cos,
    apiPitchType: p.auto_pitch_type,
    stuffPlus: p.stuff_plus === null ? null : round1(p.stuff_plus),
    locationPlus: p.location_plus === null ? null : round1(p.location_plus),
    pitchingPlus: p.pitching_plus === null ? null : round1(p.pitching_plus),
    stuffFinal: p.stuff_final == null ? null : round1(p.stuff_final),
    finalHistoryN: p.final_history_n ?? null,
    finalHistoryStatus: p.final_history_status ?? null,
  };
}

function mapArsenal(r: ApiArsenalRow, pitcherId: string): ArsenalRow | null {
  const pitchType = PITCH_TYPE_FROM_API[r.auto_pitch_type];
  const category = ALTITUDE_FROM_API[r.altitude_category];
  if (!pitchType || !category) return null;
  const stuff = r.stuff_plus;
  return {
    pitcherId,
    pitchType,
    season: 2025,
    category,
    n: r.n,
    usagePct: round1(r.usage * 100),
    veloMphAvg: round1(r.rel_speed),
    spinRpmAvg: Math.round(r.spin_rate),
    spinAxisSinAvg: r.spin_axis_sin,
    spinAxisCosAvg: r.spin_axis_cos,
    relHeightAvg: round1(r.rel_height),
    relSideAvg: round1(r.rel_side),
    extensionAvg: round1(r.extension),
    ivbInAvg: round1(r.induced_vert_break),
    hbInAvg: round1(r.horz_break),
    stuffPlus: stuff === null ? null : round1(stuff),
    stuffCi: r.ci ? [round1(r.ci[0]), round1(r.ci[1])] : null,
  };
}

function mapDelta(d: ApiDelta, pitcherId: string): ScenarioDelta | null {
  const pitchType = PITCH_TYPE_FROM_API[d.auto_pitch_type];
  const scenarioA = ALTITUDE_FROM_API[d.scenario_a];
  const scenarioB = ALTITUDE_FROM_API[d.scenario_b];
  if (!pitchType || !scenarioA || !scenarioB) return null;
  // null honesto: sin soporte el backend no estima; no se convierte a 0.
  return {
    pitcherId,
    pitchType,
    scenarioA,
    scenarioB,
    deltaStuffPlus: d.delta_score === null ? null : round1(d.delta_score),
    ci: d.ci ? [round1(d.ci[0]), round1(d.ci[1])] : null,
    nA: d.n_a,
    nB: d.n_b,
    regime: d.regime,
  };
}

export function apiPitcherToDomain(row: ApiPitcherRow): Pitcher {
  return {
    id: row.pitcher_anon_id,
    label: `Pitcher ${row.pitcher_anon_id.replace(/^pitcher_/, '')}`,
    throws: row.throws === 'Left' ? 'L' : 'R',
  };
}

export function apiBundleToDomain(b: ApiBundle): PitcherBundle {
  const pitcher: Pitcher = {
    id: b.pitcher_anon_id,
    label: `Pitcher ${b.pitcher_anon_id.replace(/^pitcher_/, '')}`,
    throws: b.throws === 'Left' ? 'L' : 'R',
  };
  return {
    pitcher,
    stuffPlus: scoreSummary(b.summaries.stuff.mean, b.summaries.stuff.ci, b.summaries.stuff.n),
    locationPlus: scoreSummary(b.summaries.location.mean, b.summaries.location.ci, b.summaries.location.n),
    pitchingPlus: scoreSummary(b.summaries.pitching.mean, b.summaries.pitching.ci, b.summaries.pitching.n),
    spin: {
      avgRpm: Math.round(b.spin.avg_rpm),
      maxRpm: Math.round(b.spin.max_rpm),
      axisDeg: Math.round(b.spin.axis_deg),
    },
    arsenal: b.arsenal.map((r) => mapArsenal(r, b.pitcher_anon_id)).filter((r): r is ArsenalRow => r !== null),
    pitches: b.pitches.map((p) => mapPitch(p, b.pitcher_anon_id)).filter((p): p is PitchScore => p !== null),
    deltas: b.deltas
      .filter((d) => d.delta_score !== null || d.regime === 'insuficiente')
      .map((d) => mapDelta(d, b.pitcher_anon_id))
      .filter((d): d is ScenarioDelta => d !== null),
  };
}
