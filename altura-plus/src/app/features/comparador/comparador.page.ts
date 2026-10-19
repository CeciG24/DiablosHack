import { Component, computed, effect, inject, signal } from '@angular/core';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ApiService, ApiProfile } from '../../core/api/api.service';
import {
  ALTITUDE_CATEGORIES,
  AltitudeCategory,
  PitchType,
} from '../../core/models/domain.types';
import { PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import { TileComponent } from '../../shared/ui/tile.component';
import { MovementChartComponent } from '../../shared/ui/movement-chart.component';
import { TrajectoryComponent } from '../../shared/ui/trajectory.component';
import { StateBannerComponent } from '../../shared/ui/state-banner.component';

/**
 * Escenarios posibles: Ruta A compara categorías; Ruta B (metadatos simulados) nombra parques.
 * Sin stadium_id en el dataset, 'Extreme' es solo un proxy de parques altos tipo CDMX —
 * NO identifica al Harp Helú. El disclaimer es obligatorio donde se use.
 */
const STADIUM_B: Record<AltitudeCategory, string> = {
  Extreme: 'Extremo (~CDMX, proxy — sin stadium_id)',
  Medium: 'Medio (~1 000 m, proxy)',
  'No Altitude': 'Bajo (< 500 m, proxy)',
};

@Component({
  selector: 'app-comparador-page',
  imports: [TileComponent, MovementChartComponent, TrajectoryComponent, StateBannerComponent],
  templateUrl: './comparador.page.html',
  styleUrl: './comparador.page.scss',
})
export class ComparadorPage {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  private readonly api = inject(ApiService);
  protected readonly categories = ALTITUDE_CATEGORIES;

  /** Agregados de liga del perfil F10 (fallback cuando el pitcher no tiene soporte). */
  readonly profile = signal<ApiProfile | null>(null);

  constructor() {
    effect(() => {
      if (this.data.source() === 'api') {
        void this.api.profile().then((p) => this.profile.set(p)).catch(() => this.profile.set(null));
      } else {
        this.profile.set(null);
      }
    });
  }

  protected readonly catA = signal<AltitudeCategory>('Extreme');
  protected readonly catB = signal<AltitudeCategory>('No Altitude');
  protected readonly sameLocation = signal(false);

  readonly bundle = computed(() => this.data.bundleOf(this.ctx.pitcherId()));

  readonly pitchesOf = (cat: AltitudeCategory) => computed(() => {
    const b = this.bundle();
    if (!b) return [];
    const type = this.ctx.pitchType();
    return b.pitches.filter(
      (p) => p.category === cat && (type === 'ALL' || p.pitchType === type),
    );
  });

  readonly pitchesA = computed(() => this.pitchesOf(this.catA())());
  readonly pitchesB = computed(() => this.pitchesOf(this.catB())());

  /** Stuff+ promedio observado por escenario a partir del arsenal. */
  readonly stuffOf = (cat: AltitudeCategory) => computed(() => {
    const b = this.bundle();
    if (!b) return null;
    const type = this.ctx.pitchType();
    const rows = b.arsenal.filter(
      (r) => r.category === cat && (type === 'ALL' || r.pitchType === type),
    );
    const n = rows.reduce((a, r) => a + r.n, 0);
    if (n === 0) return null;
    return {
      value: Math.round(rows.reduce((a, r) => a + r.stuffPlus * r.n, 0) / n),
      n,
    };
  });

  readonly stuffA = computed(() => this.stuffOf(this.catA())());
  readonly stuffB = computed(() => this.stuffOf(this.catB())());

  /** Δ estimado desde scenario_deltas: solo categorías (Ruta A). */
  readonly delta = computed(() => {
    const b = this.bundle();
    if (!b) return null;
    const type = this.ctx.pitchType();
    const a = this.catA();
    const bCat = this.catB();
    // Solo filas con estimación real: null/insuficiente no aportan un 0 fabricado.
    const rows = b.deltas.filter(
      (d) =>
        d.deltaStuffPlus !== null && d.ci !== null && d.regime !== 'insuficiente' &&
        (type === 'ALL' || d.pitchType === type) &&
        ((d.scenarioA === a && d.scenarioB === bCat) ||
          (d.scenarioA === bCat && d.scenarioB === a)),
    );
    if (rows.length === 0) return null;
    const nA = rows.reduce((x, d) => x + d.nA, 0);
    const nB = rows.reduce((x, d) => x + d.nB, 0);
    const minN = Math.min(...rows.map((d) => Math.min(d.nA, d.nB)));
    const regime = minN >= 120 ? 'interpolado' : minN >= 40 ? 'extrapolado' : 'insuficiente';
    // delta canónico = B − A; el panel muestra "A − B" → cada fila se orienta sola.
    const oriented = rows.map((d) => {
      const s = d.scenarioA === a ? -1 : 1;
      return { delta: s * d.deltaStuffPlus!, lo: s * d.ci![0], hi: s * d.ci![1] };
    });
    const w = oriented.reduce((x, r) => x + 1 / Math.max(r.hi - r.lo, 1), 0);
    const deltaW = oriented.reduce((x, r) => x + (r.delta / Math.max(r.hi - r.lo, 1)), 0) / Math.max(w, 0.01);
    const lo = Math.min(...oriented.map((r) => Math.min(r.lo, r.hi)));
    const hi = Math.max(...oriented.map((r) => Math.max(r.lo, r.hi)));
    return { delta: Math.round(deltaW * 10) / 10, ci: [lo, hi] as const, nA, nB, regime };
  });

  /**
   * Fallback de liga: el pitcher casi nunca tiene historial multi-categoría ni
   * simulaciones propias suficientes. Cuando el delta del pitcher no es
   * estimable, se muestra el agregado de /profile (NoAlt→Extreme) etiquetado
   * como liga — nunca como señal del pitcher.
   */
  readonly leagueDelta = computed(() => {
    const prof = this.profile();
    if (!prof) return null;
    const a = this.catA();
    const bCat = this.catB();
    const pair = new Set([a, bCat]);
    if (!(pair.has('No Altitude') && pair.has('Extreme'))) return null;
    const type = this.ctx.pitchType();
    const typeApi = type === 'ALL' ? null : PITCH_TYPE_TO_API[type];
    const rows = prof.by_pitch_type.filter((r) => typeApi === null || r.auto_pitch_type === typeApi);
    if (rows.length === 0) return null;
    const n = rows.reduce((x, r) => x + r.n, 0);
    // profile delta = Extreme − NoAlt; el panel muestra A − B.
    const oriented = a === 'Extreme' ? 1 : -1;
    const delta =
      oriented * rows.reduce((x, r) => x + r.delta_score * r.n, 0) / n;
    return { delta: Math.round(delta * 10) / 10, n };
  });

  /** ¿Mostrar el fallback de liga? Solo si el delta propio no es estimable. */
  readonly showLeagueFallback = computed(
    () => this.leagueDelta() !== null && (this.delta() === null || this.delta()!.regime === 'insuficiente'),
  );

  scenarioLabel(cat: AltitudeCategory): string {
    return this.ctx.routeMode() === 'B' ? STADIUM_B[cat] : cat;
  }

  sampleOf(cat: AltitudeCategory) {
    const list = cat === this.catA() ? this.pitchesA() : this.pitchesB();
    const p = list[0];
    return p
      ? { veloMph: p.veloMph, ivbIn: p.ivbIn, hbIn: p.hbIn, plateXIn: p.plateXIn, plateZIn: p.plateZIn }
      : null;
  }

  toggleRouteB(): void {
    this.ctx.routeMode.set(this.ctx.routeMode() === 'A' ? 'B' : 'A');
  }
}
