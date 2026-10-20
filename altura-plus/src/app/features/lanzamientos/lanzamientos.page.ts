import { Component, computed, effect, ElementRef, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { ALTITUDE_LABELS, PITCH_TYPE_NAMES, PitchScore } from '../../core/models/domain.types';
import { DEFAULT_FILTERS, PitchFilters, filterPitches, mean, metric, pitchMetrics } from '../../core/models/pitch-analysis';
import { PitchFiltersComponent } from '../../shared/ui/pitch-filters.component';
import { MovementChartComponent, PITCH_COLORS } from '../../shared/ui/movement-chart.component';
import { StrikeZoneComponent } from '../../shared/ui/strike-zone.component';
import { PitchEvaluationService, PitchProbabilities, PitchTarget, pitchTargetRows } from './pitch-evaluation.service';

const EXTREMES_N = 8;

type SortKey = 'idx' | 'pitcher' | 'season' | 'category' | 'type' | 'stuff' | 'location' | 'pitching' | 'final'
  | 'velo' | 'spin' | 'hb' | 'ivb' | 'ext' | 'relZ' | 'relX';
const TEXT_KEYS: ReadonlySet<SortKey> = new Set(['idx', 'pitcher', 'category', 'type']);

@Component({
  selector: 'app-lanzamientos-page',
  imports: [PitchFiltersComponent, MovementChartComponent, StrikeZoneComponent],
  providers: [PitchEvaluationService],
  templateUrl: './lanzamientos.page.html',
  styleUrl: './lanzamientos.page.scss',
})
export class LanzamientosPage {
  protected readonly data = inject(DataService);
  private readonly evaluator = inject(PitchEvaluationService);
  private readonly route = inject(ActivatedRoute);
  protected readonly labels = ALTITUDE_LABELS;
  protected readonly names = PITCH_TYPE_NAMES;
  protected readonly colors = PITCH_COLORS;
  protected readonly metric = metric;
  readonly filters = signal<PitchFilters>({ ...DEFAULT_FILTERS, pitcherId: this.route.snapshot.queryParamMap.get('pitcher') ?? 'ALL' });
  readonly allPitches = computed(() => this.data.bundles().flatMap((b) => b.pitches));
  readonly pitchers = computed(() => this.data.bundles().map((b) => b.pitcher));
  readonly seasons = computed(() => [...new Set(this.allPitches().map((p) => p.season))].sort());
  readonly pitches = computed(() => filterPitches(this.allPitches(), this.filters()));
  readonly metrics = computed(() => pitchMetrics(this.pitches()));
  readonly finalSummary = computed(() => {
    const scored = this.pitches().filter((p) => p.stuffFinal != null && Number.isFinite(p.stuffFinal));
    return {
      value: mean(scored.map((p) => p.stuffFinal)),
      n: scored.length,
      priorOnly: scored.filter((p) => p.finalHistoryStatus === 'group_prior_only').length,
    };
  });
  readonly page = signal(0);
  readonly pageSize = 20;
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.pitches().length / this.pageSize)));
  readonly sortKey = signal<SortKey>('final');
  readonly sortDir = signal<1 | -1>(-1);
  readonly pitcherLabels = computed(
    () => new Map(this.data.bundles().map((b) => [b.pitcher.id, b.pitcher.label] as const)),
  );
  readonly sortedPitches = computed(() => {
    const key = this.sortKey();
    const dir = this.sortDir();
    const labels = this.pitcherLabels();
    const val = (p: PitchScore): string | number | null => {
      switch (key) {
        case 'idx': return p.id;
        case 'pitcher': return labels.get(p.pitcherId) ?? '';
        case 'season': return p.season;
        case 'category': return p.category;
        case 'type': return p.pitchType;
        case 'stuff': return p.stuffPlus;
        case 'location': return p.locationPlus;
        case 'pitching': return p.pitchingPlus;
        case 'final': return p.stuffFinal != null && Number.isFinite(p.stuffFinal) ? p.stuffFinal : null;
        case 'velo': return p.veloMph;
        case 'spin': return p.spinRpm;
        case 'hb': return p.hbIn;
        case 'ivb': return p.ivbIn;
        case 'ext': return p.extensionFt ?? null;
        case 'relZ': return p.releaseHeightFt ?? null;
        case 'relX': return p.releaseSideFt ?? null;
      }
    };
    return [...this.pitches()].sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
  });
  /** Posición 1-based de cada pitch en la lista ordenada: un número legible
   * en lugar del hash interno para el usuario promedio. */
  readonly rowNumbers = computed(
    () => new Map(this.sortedPitches().map((p, i) => [p.id, i + 1] as const)),
  );
  readonly pagePitches = computed(() => this.sortedPitches().slice(this.page() * this.pageSize, (this.page() + 1) * this.pageSize));
  readonly selectedId = signal<string | null>(null);
  /** El detalle vive en un modal: se abre al tocar un renglón; la selección
   * (anillo en los mapas) persiste aunque el modal se cierre. */
  readonly detailOpen = signal(false);
  private readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('pitchDialog');
  readonly selected = computed<PitchScore | null>(() => this.pitches().find((p) => p.id === this.selectedId()) ?? this.pagePitches()[0] ?? null);
  readonly selectedBundle = computed(() => this.data.bundleOf(this.selected()?.pitcherId ?? ''));
  /** Modal: el pitch marcado dentro del arsenal de su lanzador como contexto. */
  readonly modalPitches = computed<readonly PitchScore[]>(() => {
    const bundle = this.selectedBundle();
    const sel = this.selected();
    if (bundle) return bundle.pitches;
    return sel ? [sel] : [];
  });
  readonly modalHighlight = computed(
    () => this.modalPitches().findIndex((p) => p.id === this.selected()?.id),
  );
  readonly chartPitches = computed(() => {
    const sample = this.pitches().slice(0, 600);
    const selected = this.selected();
    return selected && !sample.some((p) => p.id === selected.id) ? [...sample.slice(0, 599), selected] : sample;
  });
  readonly highlightIndex = computed(() => this.chartPitches().findIndex((p) => p.id === this.selected()?.id));
  /** Top/bottom explícito por Pitching+ sobre la muestra visible del mapa.
   * best y worst nunca comparten índices; pocos pitches scoreados → null. */
  readonly extremes = computed(() => {
    const scored = this.chartPitches()
      .map((p, i) => ({ i, s: p.pitchingPlus }))
      .filter((x): x is { i: number; s: number } => x.s !== null && Number.isFinite(x.s))
      .sort((a, b) => b.s - a.s);
    if (scored.length < 4) return null;
    const k = Math.min(EXTREMES_N, Math.floor(scored.length / 2));
    const best = scored.slice(0, k).map((x) => x.i);
    const worst = scored.slice(-k).map((x) => x.i).filter((i) => !best.includes(i));
    return { best, worst };
  });
  readonly legend = computed(() => [...new Set(this.chartPitches().map((p) => p.pitchType))]);
  readonly probabilities = signal<PitchProbabilities | null>(null);
  readonly targetRows = computed(() => pitchTargetRows(this.probabilities()));
  readonly probabilityStatus = signal<'loading' | 'ready' | 'missing' | 'error'>('missing');
  readonly probabilityAttempt = signal(0);

  constructor() {
    effect(() => {
      const el = this.dialog()?.nativeElement;
      if (!el) return;
      const open = this.detailOpen();
      if (open && !el.open) {
        el.showModal();
        el.scrollTop = 0;
      }
      if (!open && el.open) el.close();
    });
    effect((cleanup) => {
      const pitch = this.selected();
      const bundle = this.selectedBundle();
      const source = this.data.source();
      this.probabilityAttempt();
      let active = true;
      cleanup(() => { active = false; });
      this.probabilities.set(null);
      if (!pitch || !bundle || source !== 'api') {
        this.probabilityStatus.set('missing');
        return;
      }
      this.probabilityStatus.set('loading');
      void this.evaluator.evaluate(pitch, bundle.pitcher.throws).then((result) => {
        if (!active) return;
        this.probabilities.set(result);
        this.probabilityStatus.set(result ? 'ready' : 'missing');
      }).catch(() => { if (active) this.probabilityStatus.set('error'); });
    });
  }

  updateFilters(filters: PitchFilters): void {
    this.filters.set(filters);
    this.page.set(0);
    this.selectedId.set(null);
    this.detailOpen.set(false);
  }

  setSort(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortDir.update((d) => (d === 1 ? -1 : 1) as 1 | -1);
    } else {
      this.sortKey.set(key);
      // Texto ascendente por defecto; numérico descendente.
      this.sortDir.set(TEXT_KEYS.has(key) ? 1 : -1);
    }
    this.page.set(0);
  }

  sortIcon(key: SortKey): string {
    return this.sortKey() === key ? (this.sortDir() === 1 ? '▲' : '▼') : '';
  }

  ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
    return this.sortKey() === key ? (this.sortDir() === 1 ? 'ascending' : 'descending') : 'none';
  }

  turnPage(direction: number): void {
    this.page.update((page) => Math.max(0, Math.min(this.pageCount() - 1, page + direction)));
    this.selectedId.set(null);
  }

  openDetail(id: string): void {
    this.selectedId.set(id);
    this.detailOpen.set(true);
  }

  closeDetail(): void { this.detailOpen.set(false); }

  /** Click en el fondo del dialog (fuera del contenido) = cerrar. */
  onDialogBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.closeDetail();
  }

  targetValue(target: PitchTarget): string {
    if (target.value === null) return 'No disponible';
    return target.format === 'runs' ? metric(target.value, 2) + ' carreras' : metric(target.value * 100) + '%';
  }

  retryProbabilities(): void { this.probabilityAttempt.update((attempt) => attempt + 1); }
}
