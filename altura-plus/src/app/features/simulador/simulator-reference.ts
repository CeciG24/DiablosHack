import { PitchScore } from '../../core/models/domain.types';

/** Quantiles use the full cohort, not the capped display sample. */
export function movementReference(pitches: readonly PitchScore[]) {
  const scored = pitches.filter((p) => p.stuffPlus != null && Number.isFinite(p.stuffPlus) &&
    Number.isFinite(p.hbIn) && Number.isFinite(p.ivbIn))
    .sort((a, b) => a.stuffPlus! - b.stuffPlus! || a.id.localeCompare(b.id));
  const n = scored.length;
  const size = Math.min(n, 360);
  const sample = Array.from({ length: size }, (_, i) =>
    scored[size === 1 ? 0 : Math.floor(i * (n - 1) / (size - 1))]);
  if (n < 20) return { n, sample, extremes: null };
  const k = Math.floor(n / 10);
  const low = scored[k - 1].stuffPlus!;
  const high = scored[n - k].stuffPlus!;
  if (low >= high) return { n, sample, extremes: null };
  return {
    n, sample,
    extremes: {
      best: sample.flatMap((p, i) => p.stuffPlus! >= high ? [i] : []),
      worst: sample.flatMap((p, i) => p.stuffPlus! <= low ? [i] : []),
    },
  };
}
