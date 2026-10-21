import { MetricGuideComponent } from '../../shared/ui/metric-guide.component';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPE_NAMES, PitchType } from '../../core/models/domain.types';
import { arsenalByType, metric } from '../../core/models/pitch-analysis';

@Component({
  selector: 'app-lanzadores-page',
  imports: [MetricGuideComponent, RouterLink],
  templateUrl: './lanzadores.page.html',
})
export class LanzadoresPage {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  protected readonly metric = metric;
  protected readonly labels = ALTITUDE_LABELS;
  protected readonly names = PITCH_TYPE_NAMES;
  readonly search = signal('');
  readonly season = signal(2025);
  readonly comparisonType = signal<PitchType | 'ALL'>('ALL');
  readonly bundle = computed(() => this.data.bundleOf(this.ctx.pitcherId()));
  readonly pitchers = computed(() => this.data.bundles()
    .filter((b) => b.pitcher.label.toLowerCase().includes(this.search().toLowerCase()))
    .sort((a, b) => Number(b.stuffPlus.modelAvailable) - Number(a.stuffPlus.modelAvailable) || b.stuffPlus.value - a.stuffPlus.value));
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

  setSearch(event: Event): void { this.search.set((event.target as HTMLInputElement).value); }
  setSeason(event: Event): void { this.season.set(Number((event.target as HTMLSelectElement).value)); }
  setType(event: Event): void { this.comparisonType.set((event.target as HTMLSelectElement).value as PitchType | 'ALL'); }
}
