import { AltitudeCategory, PitchType } from './domain.types';

export type CandidateMode = 'pitches' | 'profiles';
export type Hand = 'Right' | 'Left';
export type ReferenceSeason = '2025' | '2026' | '2025-2026';
export type PhysicalKey = 'veloMph' | 'spinRpm' | 'ivbIn' | 'hbIn' | 'extensionFt' | 'releaseHeightFt' | 'releaseSideFt' | 'axisDeg';
export interface CandidateRow extends Record<PhysicalKey, number | null> {
  key: string;
  type: PitchType;
  category: AltitudeCategory;
  usage: number | null;
  n: number | null;
  year?: number;
}
export interface Candidate {
  name: string;
  hand: Hand;
  mode: CandidateMode;
  rows: CandidateRow[];
  provenance: string;
}
export interface ProfilerPayload {
  mode: CandidateMode;
  target: string;
  entries: { key: string; pitch: Record<string, unknown>; weight: number; observed_n: number | null }[];
}
export interface ProfileSummary {
  source_score: number | null;
  target_score: number | null;
  paired_source_score: number | null;
  delta: number | null;
  coverage: number;
  weight: number;
  supported_weight: number;
  entries: number;
  observed_n: number;
  interval: null;
}
export interface ProfileResultRow {
  key: string;
  auto_pitch_type: string;
  source: string;
  weight: number;
  source_score: number | null;
  target_score: number | null;
  delta: number | null;
  target_ivb: number | null;
  target_hb: number | null;
  status: string;
  reason: string | null;
  warnings: string;
}
export interface ProfilerEvaluation {
  mode: CandidateMode;
  target: string;
  release_id: string;
  representative: boolean;
  arsenal_in_model: false;
  summary: ProfileSummary;
  groups: (ProfileSummary & { auto_pitch_type: string })[];
  records: ProfileResultRow[];
}
export interface ProfilerReference {
  years: number[];
  hand: Hand;
  data_run: string;
  raw_n: number;
  complete_n: number;
  excluded_n: number;
  by_year: Record<string, number>;
  groups: { auto_pitch_type: string; n: number; pitchers: number;
    quantiles: Record<string, Record<'p10' | 'p25' | 'p50' | 'p75' | 'p90', number>> }[];
  points: { auto_pitch_type: string; year: number; ivb: number; hb: number; velo: number }[];
}
export interface EvaluationSnapshot {
  candidate: Candidate;
  target: AltitudeCategory;
  result: ProfilerEvaluation;
  fingerprint: string;
  referenceYears: ReferenceSeason;
  evaluatedAt: string;
}
