import { MetricGuideComponent } from '../../shared/ui/metric-guide.component';
import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPE_NAMES, PitchType, PitcherBundle } from '../../core/models/domain.types';
import { arsenalByType, metric } from '../../core/models/pitch-analysis';

type SortKey = 'label' | 'throws' | 'n' | 'stuff' | 'location' | 'pitching';

@Component({
  selector: 'app-lanzadores-page',
  imports: [MetricGuideComponent, RouterLink],
  templateUrl: './lanzadores.page.html',
  styleUrl: './lanzadores.page.scss',
})
export class LanzadoresPage {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  protected readonly metric = metric;
  protected readonly labels = ALTITUDE_LABELS;
  protected readonly names = PITCH_TYPE_NAMES;
  readonly search = signal('');
  /** Por defecto sólo pitchers con muestra suficiente (n ≥ 120, mismo umbral
   * que la lectura de scouting "Ampliar muestra"). */
  readonly onlySufficient = signal(true);
  readonly season = signal(2025);
  readonly comparisonType = signal<PitchType | 'ALL'>('ALL');
  readonly sortKey = signal<SortKey>('stuff');
  readonly sortDir = signal<1 | -1>(-1);
  readonly bundle = computed(() => this.data.bundleOf(this.ctx.pitcherId()));
  readonly pitchers = computed(() => {
    const key = this.sortKey();
    const dir = this.sortDir();
    const val = (b: PitcherBundle): string | number | null =>
      key === 'label' ? b.pitcher.label
      : key === 'throws' ? b.pitcher.throws
      : key === 'n' ? b.stuffPlus.n
      : key === 'location' ? (b.locationPlus.modelAvailable ? b.locationPlus.value : null)
      : key === 'pitching' ? (b.pitchingPlus.modelAvailable ? b.pitchingPlus.value : null)
      : (b.stuffPlus.modelAvailable ? b.stuffPlus.value : null);
    return this.data.bundles()
      .filter((b) => b.pitcher.label.toLowerCase().includes(this.search().toLowerCase()))
      .filter((b) => !this.onlySufficient() || b.stuffPlus.n >= 120)
      .sort((a, b) => {
        const va = val(a), vb = val(b);
        if (va === null && vb === null) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
      });
  });
  /** Ficha en modal: el lanzador queda seleccionado en el contexto y su renglón
   * marcado aunque el modal se cierre. */
  readonly detailOpen = signal(false);
  private readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('pitcherDialog');
  readonly seasons = computed(() => [...new Set(this.bundle()?.arsenal.map((r) => r.season) ?? [])].sort());
  readonly arsenalRows = computed(() => this.bundle()?.arsenal.filter((r) => r.season === this.season()) ?? []);
  readonly arsenal = computed(() => arsenalByType(this.arsenalRows()));
  readonly baseline = computed(() => this.arsenal().find((r) => r.type === 'FB') ?? this.arsenal().find((r) => r.type === 'SI') ?? null);
  readonly relationships = computed(() => this.arsenal().map((r) => {
    const base = this.baseline();
    return { ...r, deltaVelo: base ? r.velo - base.velo : null, deltaHb: base ? r.hb - base.hb : null, deltaIvb: base ? r.ivb - base.ivb : null };
  }));
  readonly comparison = computed(() => ALTITUDE_CATEGORIES.map((category) => {
    const rows = this.arsenalRows().filter((r) => r.category === category &&
      (this.comparisonType() === 'ALL' || r.pitchType === this.comparisonType()));
    const scored = rows.filter((r) => r.stuffPlus !== null);
    const n = rows.reduce((sum, r) => sum + r.n, 0);
    const scoredN = scored.reduce((sum, r) => sum + r.n, 0);
    return {
      category, n,
      stuff: scoredN ? scored.reduce((sum, r) => sum + (r.stuffPlus ?? 0) * r.n, 0) / scoredN : null,
    };
  }));
  readonly deltas = computed(() => this.bundle()?.deltas.filter((d) =>
    d.scenarioA === 'No Altitude' && d.scenarioB === 'Extreme' ||
    d.scenarioB === 'No Altitude' && d.scenarioA === 'Extreme').map((d) => ({
      ...d,
      delta: d.deltaStuffPlus === null ? null : (d.scenarioB === 'Extreme' ? d.deltaStuffPlus : -d.deltaStuffPlus),
    })).filter((d) => this.comparisonType() === 'ALL' || d.pitchType === this.comparisonType()) ?? []);

  constructor() {
    effect(() => {
      const el = this.dialog()?.nativeElement;
      if (!el) return;
      const open = this.detailOpen();
      if (open && !el.open) { el.showModal(); el.scrollTop = 0; }
      if (!open && el.open) el.close();
    });
  }

  openProfile(id: string): void {
    this.ctx.selectPitcher(id);
    this.detailOpen.set(true);
  }

  closeProfile(): void { this.detailOpen.set(false); }

  /** Click en el fondo del dialog (fuera del contenido) = cerrar. */
  onDialogBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.closeProfile();
  }

  /** Chip del score: resalta perfiles físicos favorables sin inventar jerarquías. */
  scoreClass(value: number | null): string {
    if (value === null) return 'score score--none';
    if (value >= 105) return 'score score--hot';
    if (value >= 100) return 'score score--warm';
    return 'score';
  }

  readTag(b: PitcherBundle): { text: string; hot: boolean } {
    return b.stuffPlus.modelAvailable && b.stuffPlus.value >= 105 && b.stuffPlus.n >= 120
      ? { text: 'Perfil físico favorable', hot: true }
      : b.stuffPlus.n < 120 ? { text: 'Ampliar muestra', hot: false } : { text: 'Explorar repertorio', hot: false };
  }

  setSort(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortDir.update((d) => (d === 1 ? -1 : 1) as 1 | -1);
      return;
    }
    this.sortKey.set(key);
    // Numérico por defecto descendente; texto ascendente.
    this.sortDir.set(key === 'label' || key === 'throws' ? 1 : -1);
  }

  sortIcon(key: SortKey): string {
    return this.sortKey() === key ? (this.sortDir() === 1 ? '▲' : '▼') : '';
  }

  ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
    return this.sortKey() === key ? (this.sortDir() === 1 ? 'ascending' : 'descending') : 'none';
  }

  setSearch(event: Event): void { this.search.set((event.target as HTMLInputElement).value); }
  setOnlySufficient(event: Event): void { this.onlySufficient.set((event.target as HTMLInputElement).checked); }
  setSeason(event: Event): void { this.season.set(Number((event.target as HTMLSelectElement).value)); }
  setType(event: Event): void { this.comparisonType.set((event.target as HTMLSelectElement).value as PitchType | 'ALL'); }
}
