import { Component, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { ALTITUDE_LABELS, PITCH_TYPE_NAMES, PitchScore } from '../../core/models/domain.types';
import { DEFAULT_FILTERS, PitchFilters, filterPitches, metric, pitchMetrics } from '../../core/models/pitch-analysis';
import { PitchFiltersComponent } from '../../shared/ui/pitch-filters.component';
import { MovementChartComponent, PITCH_COLORS } from '../../shared/ui/movement-chart.component';
import { StrikeZoneComponent } from '../../shared/ui/strike-zone.component';
import { PitchEvaluationService, PitchProbabilities } from './pitch-evaluation.service';

@Component({
  selector: 'app-lanzamientos-page',
  imports: [PitchFiltersComponent, MovementChartComponent, StrikeZoneComponent],
  providers: [PitchEvaluationService],
  templateUrl: './lanzamientos.page.html',
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
  readonly page = signal(0);
  readonly pageSize = 20;
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.pitches().length / this.pageSize)));
  readonly pagePitches = computed(() => this.pitches().slice(this.page() * this.pageSize, (this.page() + 1) * this.pageSize));
  readonly selectedId = signal<string | null>(null);
  readonly selected = computed<PitchScore | null>(() => this.pitches().find((p) => p.id === this.selectedId()) ?? this.pagePitches()[0] ?? null);
  readonly selectedBundle = computed(() => this.data.bundleOf(this.selected()?.pitcherId ?? ''));
  readonly chartPitches = computed(() => {
    const sample = this.pitches().slice(0, 600);
    const selected = this.selected();
    return selected && !sample.some((p) => p.id === selected.id) ? [...sample.slice(0, 599), selected] : sample;
  });
  readonly highlightIndex = computed(() => this.chartPitches().findIndex((p) => p.id === this.selected()?.id));
  readonly legend = computed(() => [...new Set(this.chartPitches().map((p) => p.pitchType))]);
  readonly probabilities = signal<PitchProbabilities | null>(null);
  readonly probabilityStatus = signal<'loading' | 'ready' | 'missing' | 'error'>('missing');
  readonly probabilityAttempt = signal(0);

  constructor() {
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
  }

  turnPage(direction: number): void {
    this.page.update((page) => Math.max(0, Math.min(this.pageCount() - 1, page + direction)));
    this.selectedId.set(null);
  }

  percent(value: number | null | undefined): string {
    return value != null ? metric(value * 100) + '%' : '\u2014';
  }

  retryProbabilities(): void { this.probabilityAttempt.update((attempt) => attempt + 1); }
}
