import { inject, Injectable, signal } from '@angular/core';
import {
  PitcherBundle,
  SimulatorExample,
} from '../models/domain.types';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from './synthetic-data';
import { ApiService } from '../api/api.service';
import { apiBundleToDomain, apiPitcherToDomain } from '../api/api-mappers';
import { ScoutingContextService } from '../state/scouting-context.service';

export type DataStatus = 'loading' | 'ready' | 'error';
export type DataSource = 'api' | 'synthetic';

interface ContractArtifacts {
  scoresPitch?: unknown;
  pitcherArsenal?: unknown;
  scenarioDeltas?: unknown;
  syntheticExamples?: SimulatorExample[];
}

/**
 * Fuente de datos del dashboard.
 * - Si el backend FastAPI responde (/health + /api/v1/pitchers), se usan
 *   pitchers reales del review 2025 con scores F8 y deltas F10.
 * - Si no, cae al generador sintético determinista (demo offline) y el
 *   estado `source` lo deja explícito para que la UI nunca presente los
 *   números sintéticos como evidencia del modelo.
 */
@Injectable({ providedIn: 'root' })
export class DataService {
  private readonly api = inject(ApiService);
  private readonly ctx = inject(ScoutingContextService);

  readonly status = signal<DataStatus>('loading');
  readonly source = signal<DataSource | null>(null);
  readonly bundles = signal<readonly PitcherBundle[]>([]);
  readonly examples = signal<readonly SimulatorExample[]>([]);
  readonly artifactsMissing = signal<readonly string[]>([]);
  readonly errorMessage = signal<string | null>(null);

  constructor() {
    void this.load();
  }

  bundleOf(pitcherId: string): PitcherBundle | undefined {
    return this.bundles().find((b) => b.pitcher.id === pitcherId);
  }

  async reload(): Promise<void> {
    await this.load();
  }

  private async load(): Promise<void> {
    this.status.set('loading');
    this.errorMessage.set(null);
    const artifacts = await this.fetchArtifacts();
    this.examples.set(artifacts.syntheticExamples ?? DEFAULT_EXAMPLES);

    if (await this.api.health()) {
      try {
        const bundles = await this.loadApiBundles();
        if (bundles.length > 0) {
          this.bundles.set(bundles);
          this.source.set('api');
          if (!this.bundleOf(this.ctx.pitcherId())) {
            this.ctx.selectPitcher(bundles[0].pitcher.id);
          }
          this.status.set('ready');
          return;
        }
      } catch (err) {
        // El API respondió health pero falló el bundle: se registra y cae a sintético.
        console.warn('API disponible pero el bundle falló; usando sintético.', err);
      }
    }

    this.bundles.set(SYNTHETIC_PITCHERS.map((p) => buildSyntheticBundle(p)));
    this.source.set('synthetic');
    this.status.set('ready');
  }

  private async loadApiBundles(): Promise<PitcherBundle[]> {
    const { records } = await this.api.pitchers(60, 60);
    // Priorizar pitchers con cobertura multi-categoría (≥2 escenarios de
    // altitud) para que el comparador tenga contraste real; completar con el
    // resto por score si faltan.
    const sorted = [...records].sort(
      (a, b) => b.n_categories - a.n_categories || b.experimental_score - a.experimental_score,
    );
    const picked = [
      ...sorted.filter((r) => r.n_categories >= 2),
      ...sorted.filter((r) => r.n_categories < 2),
    ].slice(0, 8);
    const results = await Promise.allSettled(
      picked.map((r) => this.api.bundle(r.pitcher_anon_id)),
    );
    const bundles = results
      .filter((r): r is PromiseFulfilledResult<import('../api/api.service').ApiBundle> => r.status === 'fulfilled')
      .map((r) => apiBundleToDomain(r.value));
    // Conservar solo pitchers con algo de cobertura real.
    return bundles.filter((b) => b.pitches.length > 0);
  }

  private async fetchArtifacts(): Promise<ContractArtifacts> {
    const missing: string[] = [];
    const get = async <T>(file: string): Promise<T | undefined> => {
      try {
        const res = await fetch(`data/${file}`, { cache: 'no-store' });
        if (!res.ok) {
          missing.push(file);
          return undefined;
        }
        return (await res.json()) as T;
      } catch {
        missing.push(file);
        return undefined;
      }
    };

    const artifacts: ContractArtifacts = {
      scoresPitch: await get<unknown>('scores_pitch.json'),
      pitcherArsenal: await get<unknown>('pitcher_arsenal.json'),
      scenarioDeltas: await get<unknown>('scenario_deltas.json'),
      syntheticExamples: await get<SimulatorExample[]>('synthetic_examples.json'),
    };
    this.artifactsMissing.set(missing);
    return artifacts;
  }
}

const DEFAULT_EXAMPLES: SimulatorExample[] = [
  { label: 'FB élite', pitchType: 'FB', veloMph: 95, spinRpm: 2450, ivbIn: 17, hbIn: -6, plateXIn: 0, plateZIn: 30 },
  { label: 'SL barrido', pitchType: 'SL', veloMph: 84, spinRpm: 2550, ivbIn: 1.5, hbIn: 8, plateXIn: 8, plateZIn: 18 },
];
