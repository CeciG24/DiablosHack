import { Injectable, signal } from '@angular/core';

/**
 * Cliente del backend FastAPI (`backend/main.py`).
 * Base configurable: `window.__DIABLOS_API__` o localStorage `diablos.api`,
 * default http://127.0.0.1:8001 (uvicorn local).
 */

export interface ApiPitcherRow {
  pitcher_anon_id: string;
  throws: 'Right' | 'Left' | null;
  n: number;
  games: number;
  n_categories: number;
  has_2026: boolean;
  experimental_score: number;
}

export interface ApiPitch {
  pitch_uid: string;
  auto_pitch_type: string;
  year: number;
  altitude_category: string;
  rel_speed: number;
  spin_rate: number;
  spin_axis_sin: number;
  spin_axis_cos: number;
  rel_height: number;
  rel_side: number;
  extension: number;
  induced_vert_break: number;
  horz_break: number;
  plate_loc_height: number;
  plate_loc_side: number;
  balls?: number | null;
  strikes?: number | null;
  batter_side?: 'Left' | 'Right' | null;
  stuff_plus: number | null;
  location_plus: number | null;
  pitching_plus: number | null;
  stuff_final?: number | null;
  final_history_n?: number | null;
  final_history_status?: 'regularized_2024_history' | 'group_prior_only' | null;
  experimental_score: number | null;
  partition?: 'phase_review' | 'test_2026';
}

export interface ApiArsenalRow {
  auto_pitch_type: string;
  altitude_category: string;
  n: number;
  usage: number;
  rel_speed: number;
  spin_rate: number;
  spin_axis_sin: number;
  spin_axis_cos: number;
  rel_height: number;
  rel_side: number;
  extension: number;
  induced_vert_break: number;
  horz_break: number;
  stuff_plus: number | null;
  ci: [number, number] | null;
}

export interface ApiDelta {
  auto_pitch_type: string;
  scenario_a: string;
  scenario_b: string;
  delta_score: number | null;
  ci: [number, number] | null;
  n_a: number;
  n_b: number;
  n_simulated: number;
  regime: 'interpolado' | 'extrapolado' | 'insuficiente';
  score_version?: string;
  scope?: string;
}

export interface ApiBundle {
  pitcher_anon_id: string;
  throws: 'Right' | 'Left' | null;
  n: number;
  games: number;
  spin: { avg_rpm: number; max_rpm: number; axis_deg: number };
  summaries: Record<'stuff' | 'location' | 'pitching', { mean: number | null; ci: [number, number] | null; n: number }>;
  arsenal: ApiArsenalRow[];
  pitches: ApiPitch[];
  deltas: ApiDelta[];
  scope: string;
}

export interface ApiPredictionFamily {
  xrv?: {
    status: string;
    runs_per_pitch: number | null;
    runs_per_100: number | null;
    baseline_runs_per_pitch: number | null;
    delta_vs_count_baseline: number | null;
    version: string;
  };
  status: string;
  score: number | null;
  warnings: string;
  score_version: string;
  provisional: boolean;
  probabilities?: Record<string, number | null>;
  conditional_probabilities?: Record<string, number | null>;
  contact_status?: string;
  contact_route?: string;
  groundball_status?: string;
  groundball_route?: string;
  chase_status?: string;
  chase_route?: string;
  p_chase_given_outside?: number | null;
}

export interface ApiPredictResponse {
  release_id: string;
  records: { stuff?: ApiPredictionFamily; location?: ApiPredictionFamily; pitching?: ApiPredictionFamily }[];
}

export interface ApiFinalScore {
  status: 'experimental' | 'invalid_input';
  score: number | null;
  probabilities: Record<string, number> | null;
  score_version: string;
  model_id: string;
  history_status: 'regularized_2024_history' | 'group_prior_only' | null;
  history_n: number;
  warnings: string;
  experimental: boolean;
}

export interface ApiSimRecord {
  status: string;
  reason: string | null;
  source_score: number | null;
  target_score: number | null;
  delta_score: number | null;
  target_ivb: number | null;
  target_hb: number | null;
  scope: string;
  score_version: string;
}

export interface ApiSimulateResponse {
  experimental: boolean;
  records: ApiSimRecord[];
}

export interface ApiRecommendationResponse {
  supported: number;
  unsupported: number;
  ranked_candidates: {
    input_index: number;
    profile: { auto_pitch_type: string };
    simulation: ApiSimRecord;
  }[];
}

export interface ApiScoutingRow {
  pitcher_anon_id: string;
  auto_pitch_type: string;
  n: number;
  games: number;
  score: number;
  provisional: boolean;
  scope: string;
}

/** docs/F10_IDEAL_PROFILE.json — agregados F10 por tipo de pitch. */
export interface ApiProfile {
  pair_focus: string;
  n_simulated: number;
  global_delta_hard_contact_bip_pp: number;
  scope: string;
  by_pitch_type: {
    auto_pitch_type: string; n: number; delta_score: number;
    delta_ivb_in: number; delta_hb_in: number;
    delta_hard_contact_bip_pp: number; delta_groundball_bip_pp: number;
  }[];
  prospect_profile: {
    auto_pitch_type: string;
    resists: { velo_mph: number; spin_rpm: number; ivb_in: number; hb_in: number; extension_ft: number; delta_score_mean: number };
    drops: { velo_mph: number; spin_rpm: number; ivb_in: number; hb_in: number; extension_ft: number; delta_score_mean: number };
    corr_delta_with: Record<string, number>;
  }[];
  answers: { q1_ganan_en_altura: string; q2_pierden_en_altura: string; q3_perfil_prospecto: string };
  caveats: string[];
}

declare global {
  interface Window { __DIABLOS_API__?: string }
}

function baseUrl(): string {
  const w = typeof window !== 'undefined' ? window : undefined;
  return (
    w?.__DIABLOS_API__ ??
    w?.localStorage?.getItem('diablos.api') ??
    'http://127.0.0.1:8001'
  ).replace(/\/$/, '');
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  /** true si el backend respondió /health con ambos modelos cargados. */
  readonly available = signal<boolean | null>(null);
  readonly base = baseUrl();

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.base}${path}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  async health(): Promise<boolean> {
    try {
      const h = await this.get<{ models: { predictor: boolean; simulator: boolean } }>('/health');
      this.available.set(h.models.predictor && h.models.simulator);
      return this.available() === true;
    } catch {
      this.available.set(false);
      return false;
    }
  }

  pitchers(minN = 150, limit = 8): Promise<{ records: ApiPitcherRow[] }> {
    return this.get(`/api/v1/pitchers?min_n=${minN}&limit=${limit}`);
  }

  bundle(pitcherId: string, maxPitches = 400): Promise<ApiBundle> {
    return this.get(`/api/v1/pitcher/${encodeURIComponent(pitcherId)}?max_pitches=${maxPitches}`);
  }

  /** Ranking pitcher×tipo del review 2025 (scouting.csv F9). */
  scouting(minN = 50, limit = 15): Promise<{ scope: string; records: ApiScoutingRow[] }> {
    return this.get(`/api/v1/scouting?min_n=${minN}&limit=${limit}`);
  }

  /** Perfil ideal F10 + respuestas a las 3 preguntas de altitud del brief. */
  profile(): Promise<ApiProfile> {
    return this.get('/api/v1/profile');
  }

  predict(records: unknown[], family: 'all' | 'stuff' | 'location' | 'pitching' = 'all'): Promise<ApiPredictResponse> {
    return this.post('/api/v1/predict', { records, family });
  }

  finalScore(records: unknown[]): Promise<{ records: ApiFinalScore[] }> {
    return this.post('/api/v1/final-score', { records });
  }

  simulate(records: unknown[], target: string): Promise<ApiSimulateResponse> {
    return this.post('/api/v1/simulate', { records, target });
  }

  recommendations(records: unknown[], target: string): Promise<ApiRecommendationResponse> {
    return this.post('/api/v1/recommendations', { records, target });
  }
}
