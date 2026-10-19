import { Component, computed, inject, signal } from '@angular/core';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import {
  ALTITUDE_CATEGORIES,
  AltitudeCategory,
  ArsenalRow,
  bandFor,
  PitchScore,
  PITCH_TYPE_NAMES,
  PitchType,
  PitcherBundle,
} from '../../core/models/domain.types';
import { TileComponent } from '../../shared/ui/tile.component';
import { GaugeComponent } from '../../shared/ui/gauge.component';
import { MovementChartComponent, MovementColorMode, PITCH_COLORS } from '../../shared/ui/movement-chart.component';
import { TrajectoryComponent, TrajectoryInput } from '../../shared/ui/trajectory.component';
import { PitchTypeGridComponent, PitchTypeCell } from '../../shared/ui/pitch-type-grid.component';
import { StateBannerComponent } from '../../shared/ui/state-banner.component';

@Component({
  selector: 'app-pitcher-page',
  imports: [
    TileComponent,
    GaugeComponent,
    MovementChartComponent,
    TrajectoryComponent,
    PitchTypeGridComponent,
    StateBannerComponent,
  ],
  templateUrl: './pitcher.page.html',
  styleUrl: './pitcher.page.scss',
})
export class PitcherPage {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  protected readonly categories = ALTITUDE_CATEGORIES;
  protected readonly pitchTypeNames = PITCH_TYPE_NAMES;
  protected readonly bandFor = bandFor;

  /** Vista de trayectoria: pitch real (muestra) vs. simulado. */
  protected readonly mode = signal<'real' | 'simulated'>('real');

  /** Color del mapa de movimiento: por familia o por Stuff+ predicho. */
  protected readonly colorMode = signal<MovementColorMode>('type');

  readonly bundle = computed<PitcherBundle | undefined>(() =>
    this.data.bundleOf(this.ctx.pitcherId()),
  );

  /** Pitches filtrados por tipo/temporada/categoría seleccionados. */
  readonly filteredPitches = computed<readonly PitchScore[]>(() => {
    const b = this.bundle();
    if (!b) return [];
    const type = this.ctx.pitchType();
    const season = this.ctx.season();
    const cat = this.ctx.category();
    return b.pitches.filter(
      (p) =>
        (type === 'ALL' || p.pitchType === type) &&
        (season === 'ALL' || p.season === season) &&
        (cat === 'ALL' || p.category === cat),
    );
  });

  /** Cuántos pitches visibles son de la partición sellada 2026 (scores F8 inferidos). */
  readonly nTest2026 = computed(
    () => this.filteredPitches().filter((p) => p.partition === 'test_2026').length,
  );

  /** Celdas del grid de tipos con uso % y Stuff+ agregado del pitcher. */
  readonly pitchTypeCells = computed<readonly PitchTypeCell[]>(() => {
    const b = this.bundle();
    if (!b) return [];
    const byType = new Map<PitchType, ArsenalRow[]>();
    for (const r of b.arsenal) {
      const list = byType.get(r.pitchType) ?? [];
      list.push(r);
      byType.set(r.pitchType, list);
    }
    const totalN = b.arsenal.reduce((a, r) => a + r.n, 0);
    return [...byType.entries()].map(([type, rows]) => {
      const n = rows.reduce((a, r) => a + r.n, 0);
      const stuffW = rows.reduce((a, r) => a + r.stuffPlus * r.n, 0) / Math.max(n, 1);
      return {
        type,
        usagePct: Math.round((n / Math.max(totalN, 1)) * 100),
        stuffPlus: Math.round(stuffW),
        n,
      };
    });
  });

  /**
   * Reparto del arsenal por categoría sobre el pitcher/tipo seleccionado.
   * Ignora el filtro de categoría para no sesgar el reparto a 100%.
   */
  readonly countByCategory = computed<readonly { cat: AltitudeCategory; n: number; pct: number }[]>(() => {
    const b = this.bundle();
    if (!b) return [];
    const type = this.ctx.pitchType();
    const rows = b.arsenal.filter((r) => type === 'ALL' || r.pitchType === type);
    const total = Math.max(rows.reduce((a, r) => a + r.n, 0), 1);
    return this.categories.map((cat) => {
      const n = rows.filter((r) => r.category === cat).reduce((a, r) => a + r.n, 0);
      return { cat, n, pct: Math.round((n / total) * 100) };
    });
  });

  /** Columnas de la matriz: categorías contrastadas contra la línea base No Altitude. */
  protected readonly altCols = ALTITUDE_CATEGORIES.filter((c) => c !== 'No Altitude');

  /** Δ Stuff+ por tipo de pitch × categoría vs. No Altitude, alineado a `altCols`. */
  readonly sensitivityRows = computed(() => {
    const b = this.bundle();
    if (!b) return [];
    const type = this.ctx.pitchType();
    const byType = new Map<PitchType, Map<string, { delta: number; ci: readonly [number, number]; n: number; regime: string }>>();
    for (const d of b.deltas) {
      if (type !== 'ALL' && d.pitchType !== type) continue;
      const isA = d.scenarioA === 'No Altitude';
      const other = isA ? d.scenarioB : d.scenarioA;
      if (other === 'No Altitude') continue;
      let m = byType.get(d.pitchType);
      if (!m) { m = new Map(); byType.set(d.pitchType, m); }
      // Sin estimación real (delta null del backend) la celda queda 'insuficiente'
      // y el template muestra "Sin soporte" — los campos no se leen en esa rama.
      const noEstimate = d.deltaStuffPlus === null || d.ci === null;
      const val = d.deltaStuffPlus ?? 0;
      const ci = d.ci ?? ([0, 0] as const);
      // Convención delta = B − A; la celda muestra "otra categoría − No Altitude":
      // si A=NoAlt la celda es B−A=delta; si B=NoAlt la celda es −delta.
      m.set(other, {
        delta: isA ? val : -val,
        ci: isA ? ci : [-ci[1], -ci[0]],
        n: d.nA + d.nB,
        regime: noEstimate ? 'insuficiente' : d.regime,
      });
    }
    return [...byType.entries()].map(([pitchType, cells]) => ({
      type: pitchType,
      cells: this.altCols.map((cat) => cells.get(cat) ?? null),
    }));
  });

  readonly selectedPitch = computed<PitchScore | null>(() => this.filteredPitches()[0] ?? null);

  readonly trajectoryPitch = computed<TrajectoryInput>(() => {
    const p = this.selectedPitch();
    if (!p) return { veloMph: 0, ivbIn: 0, hbIn: 0, plateXIn: 0, plateZIn: 26 };
    const sim = this.mode() === 'simulated';
    return {
      veloMph: p.veloMph,
      ivbIn: sim ? p.ivbIn * 0.85 : p.ivbIn,
      hbIn: sim ? p.hbIn * 0.8 : p.hbIn,
      plateXIn: p.plateXIn,
      plateZIn: p.plateZIn,
    };
  });

  readonly trajectoryColor = computed(() => {
    const p = this.selectedPitch();
    return p ? PITCH_COLORS[p.pitchType] : 'var(--red)';
  });

  toggleTrajectory(mode: 'real' | 'simulated'): void {
    this.mode.set(mode);
  }

  toggleColorMode(mode: MovementColorMode): void {
    this.colorMode.set(mode);
  }

  onPitchType(type: PitchType | 'ALL'): void {
    this.ctx.selectPitchType(type);
  }

  onCategory(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.ctx.category.set(value === 'ALL' ? 'ALL' : (value as AltitudeCategory));
  }
}
