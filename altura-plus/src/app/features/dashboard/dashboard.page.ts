import { MetricGuideComponent } from '../../shared/ui/metric-guide.component';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ALTITUDE_CATEGORIES, ALTITUDE_LABELS, PITCH_TYPE_NAMES } from '../../core/models/domain.types';
import { DEFAULT_FILTERS, filterPitches, metric, pitchMetrics } from '../../core/models/pitch-analysis';
import { PitchFiltersComponent } from '../../shared/ui/pitch-filters.component';

@Component({
  selector: 'app-dashboard-page',
  imports: [MetricGuideComponent, RouterLink, PitchFiltersComponent],
  templateUrl: './dashboard.page.html',
  styleUrl: './dashboard.page.scss',
})
export class DashboardPage {
  protected readonly data = inject(DataService);
  protected readonly insights = inject(AltitudeInsightsService);
  protected readonly ctx = inject(ScoutingContextService);
  protected readonly metric = metric;
  protected readonly names = PITCH_TYPE_NAMES;
  readonly minRankingN = 120;
  readonly filters = signal({ ...DEFAULT_FILTERS });
  readonly allPitches = computed(() => this.data.bundles().flatMap((b) => b.pitches));
  readonly pitchers = computed(() => this.data.bundles().map((b) => b.pitcher));
  readonly seasons = computed(() => [...new Set(this.allPitches().map((p) => p.season))].sort());
  readonly pitches = computed(() => filterPitches(this.allPitches(), this.filters()));
  readonly metrics = computed(() => pitchMetrics(this.pitches()));
  readonly pitcherCount = computed(() => new Set(this.pitches().map((p) => p.pitcherId)).size);
  readonly categories = computed(() => ALTITUDE_CATEGORIES.map((category) => {
    const rows = this.pitches().filter((p) => p.category === category);
    return { category, label: ALTITUDE_LABELS[category], n: rows.length, ...pitchMetrics(rows) };
  }));
  readonly leaders = computed(() => this.data.bundles().map((b) => {
    const pitches = this.pitches().filter((p) => p.pitcherId === b.pitcher.id);
    const scored = pitches.filter((p) => p.stuffPlus !== null && Number.isFinite(p.stuffPlus));
    return { pitcher: b.pitcher, n: scored.length, ...pitchMetrics(scored) };
  }).filter((r) => r.n >= this.minRankingN).sort((a, b) => (b.stuff ?? -Infinity) - (a.stuff ?? -Infinity)).slice(0, 5));
  readonly pitchLeaders = computed(() => {
    const types = [...new Set(this.pitches().map((p) => p.pitchType))];
    return types.map((type) => {
      const pitches = this.pitches().filter((p) => p.pitchType === type);
      const scored = pitches.filter((p) => p.stuffPlus !== null && Number.isFinite(p.stuffPlus));
      return { type, n: scored.length, ...pitchMetrics(scored) };
    }).filter((r) => r.n >= this.minRankingN).sort((a, b) => (b.stuff ?? -Infinity) - (a.stuff ?? -Infinity)).slice(0, 5);
  });
  readonly testCount = computed(() => this.pitches().filter((p) => p.partition === 'test_2026').length);
}
