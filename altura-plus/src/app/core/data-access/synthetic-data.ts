import {
  ALTITUDE_CATEGORIES,
  AltitudeCategory,
  ArsenalRow,
  EvidenceRegime,
  Pitcher,
  PitcherBundle,
  PitchScore,
  PitchType,
  ScenarioDelta,
  ScoreSummary,
} from '../models/domain.types';

/** Generador determinista (mulberry32) para que la demo sea reproducible offline. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const round1 = (v: number) => Math.round(v * 10) / 10;

/** shape base por tipo de pitch: [veloMph, spinRpm, ivbIn, hbIn] */
const PITCH_SHAPE: Record<PitchType, readonly [number, number, number, number]> = {
  FB: [92.5, 2350, 15.5, -6],
  CT: [88.0, 2400, 5.0, 2.5],
  SI: [91.0, 2150, 9.0, -14],
  SL: [84.5, 2500, 2.0, 6],
  CB: [78.0, 2650, -9.0, 9],
  CH: [85.0, 1750, 7.0, -11],
  SP: [84.0, 1500, 3.0, -9],
  SW: [81.0, 2700, 0.5, 14],
};

/** La altitud reduce la magnitud del break (aire más delgado). */
const ALTITUDE_IVB_FACTOR: Record<AltitudeCategory, number> = {
  'No Altitude': 1.0,
  Medium: 0.88,
  Extreme: 0.72,
};
const ALTITUDE_HB_FACTOR: Record<AltitudeCategory, number> = {
  'No Altitude': 1.0,
  Medium: 0.9,
  Extreme: 0.78,
};
/** Penalización de Stuff+ por categoría (menos movimiento => pitch más bateable). */
const ALTITUDE_STUFF_PENALTY: Record<AltitudeCategory, number> = {
  'No Altitude': 0,
  Medium: 2.5,
  Extreme: 5.5,
};

const CATEGORY_N_RANGE: Record<AltitudeCategory, readonly [number, number]> = {
  'No Altitude': [180, 420],
  Medium: [90, 220],
  Extreme: [25, 140],
};

export const SYNTHETIC_PITCHERS: Pitcher[] = [
  { id: 'p-0001', label: 'Pitcher A-1024', throws: 'R' },
  { id: 'p-0002', label: 'Pitcher B-2077', throws: 'L' },
  { id: 'p-0003', label: 'Pitcher C-3390', throws: 'R' },
  { id: 'p-0004', label: 'Pitcher D-4412', throws: 'R' },
  { id: 'p-0005', label: 'Pitcher E-5826', throws: 'L' },
  { id: 'p-0006', label: 'Pitcher F-6153', throws: 'R' },
];

const SEASONS = [2024, 2025, 2026];

function regimeFor(nA: number, nB: number): EvidenceRegime {
  const min = Math.min(nA, nB);
  if (min >= 120) return 'interpolado';
  if (min >= 40) return 'extrapolado';
  return 'insuficiente';
}

function scoreSummary(rng: () => number, base: number, n: number, modelAvailable = true): ScoreSummary {
  const se = 90 / Math.sqrt(Math.max(n, 8));
  const value = round1(base + (rng() - 0.5) * 3);
  return {
    value,
    ci: [Math.round(value - 1.7 * se), Math.round(value + 1.7 * se)],
    n,
    regime: n >= 120 ? 'interpolado' : n >= 40 ? 'extrapolado' : 'insuficiente',
    modelAvailable,
    max: round1(value + 6 + rng() * 10),
    avg: round1(value - 2 - rng() * 3),
  };
}

export function buildSyntheticBundle(pitcher: Pitcher): PitcherBundle {
  const rng = mulberry32(hashSeed(pitcher.id));
  const handSign = pitcher.throws === 'R' ? 1 : -1;

  const arsenalTypes = (Object.keys(PITCH_SHAPE) as PitchType[]).filter((t, i) => {
    if (t === 'FB') return true;
    return rng() < 0.55 + i * 0.02;
  });

  const arsenal: ArsenalRow[] = [];
  const pitches: PitchScore[] = [];
  const deltas: ScenarioDelta[] = [];

  for (const type of arsenalTypes) {
    const [velo, spin, ivb, hb] = PITCH_SHAPE[type];
    const pitcherBump = (rng() - 0.35) * 8;
    const totalN = ALTITUDE_CATEGORIES.reduce((acc, cat) => {
      const [lo, hi] = CATEGORY_N_RANGE[cat];
      return acc + lo + rng() * (hi - lo);
    }, 0);

    const nByCat = new Map<AltitudeCategory, number>();
    for (const cat of ALTITUDE_CATEGORIES) {
      const [lo, hi] = CATEGORY_N_RANGE[cat];
      const n = Math.round(lo + rng() * (hi - lo));
      nByCat.set(cat, n);

      const rows = Math.min(60, Math.max(18, Math.round(n / 3)));
      const se = 90 / Math.sqrt(Math.max(n, 8));
      for (const season of SEASONS) {
        if (rng() < 0.15 && season !== 2025) continue;
        const stuff = round1(100 + pitcherBump - ALTITUDE_STUFF_PENALTY[cat] + (rng() - 0.5) * 4);
        arsenal.push({
          pitcherId: pitcher.id,
          pitchType: type,
          season,
          category: cat,
          n: Math.round(n / SEASONS.length),
          usagePct: round1((n / totalN) * 100),
          veloMphAvg: round1(velo + pitcherBump * 0.4 + (rng() - 0.5)),
          spinRpmAvg: Math.round(spin + (rng() - 0.5) * 120),
          ivbInAvg: round1(ivb * ALTITUDE_IVB_FACTOR[cat] + (rng() - 0.5)),
          hbInAvg: round1(hb * ALTITUDE_HB_FACTOR[cat] * handSign + (rng() - 0.5)),
          stuffPlus: stuff,
          stuffCi: [Math.round(stuff - 1.7 * se), Math.round(stuff + 1.7 * se)],
        });
      }

      for (let i = 0; i < rows; i++) {
        const stuff = 100 + pitcherBump - ALTITUDE_STUFF_PENALTY[cat] + (rng() - 0.5) * 18;
        pitches.push({
          id: `${pitcher.id}-${type}-${cat}-${i}`,
          pitcherId: pitcher.id,
          pitchType: type,
          season: SEASONS[Math.floor(rng() * SEASONS.length)],
          category: cat,
          veloMph: round1(velo + pitcherBump * 0.4 + (rng() - 0.5) * 4),
          spinRpm: Math.round(spin + (rng() - 0.5) * 350),
          ivbIn: round1(ivb * ALTITUDE_IVB_FACTOR[cat] + (rng() - 0.5) * 4),
          hbIn: round1(hb * ALTITUDE_HB_FACTOR[cat] * handSign + (rng() - 0.5) * 5),
          plateXIn: round1((rng() - 0.5) * 34),
          plateZIn: round1(18 + rng() * 28),
          stuffPlus: round1(stuff),
          locationPlus: round1(100 + (rng() - 0.5) * 30),
          pitchingPlus: round1(100 + pitcherBump * 0.8 - ALTITUDE_STUFF_PENALTY[cat] * 0.6 + (rng() - 0.5) * 20),
        });
      }
    }

    const pairs: [AltitudeCategory, AltitudeCategory][] = [
      ['Extreme', 'No Altitude'],
      ['Extreme', 'Medium'],
      ['Medium', 'No Altitude'],
    ];
    for (const [a, b] of pairs) {
      const nA = nByCat.get(a) ?? 0;
      const nB = nByCat.get(b) ?? 0;
      // Convención canónica igual que el backend F10: delta = score(B) − score(A)
      // = penalty[A] − penalty[B].
      const delta =
        ALTITUDE_STUFF_PENALTY[a] - ALTITUDE_STUFF_PENALTY[b] + (rng() - 0.5) * 4;
      const se = 90 * Math.sqrt(1 / Math.max(nA, 5) + 1 / Math.max(nB, 5));
      deltas.push({
        pitcherId: pitcher.id,
        pitchType: type,
        scenarioA: a,
        scenarioB: b,
        deltaStuffPlus: round1(delta),
        ci: [Math.round(delta - 1.7 * se), Math.round(delta + 1.7 * se)],
        nA,
        nB,
        regime: regimeFor(nA, nB),
      });
    }
  }

  const totalN = arsenal.reduce((acc, r) => acc + r.n, 0);
  const stuffBase = 100 + (rng() - 0.4) * 14;
  const locationAvailable = pitcher.id !== 'p-0004';

  return {
    pitcher,
    stuffPlus: scoreSummary(rng, stuffBase, totalN),
    locationPlus: scoreSummary(rng, stuffBase - 4 + rng() * 8, totalN, locationAvailable),
    pitchingPlus: scoreSummary(rng, stuffBase - 2 + rng() * 8, totalN),
    spin: {
      avgRpm: Math.round(2100 + rng() * 400),
      maxRpm: Math.round(2400 + rng() * 400),
      axisDeg: Math.round(190 + rng() * 80),
    },
    arsenal,
    pitches,
    deltas,
  };
}
