import { Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { ApiRecommendationResponse, ApiService } from '../../core/api/api.service';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { DataService } from '../../core/data-access/data.service';
import { AltitudeCategory, ALTITUDE_LABELS } from '../../core/models/domain.types';
import { metric, productText } from '../../core/models/pitch-analysis';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ALTITUDE_TO_API, arsenalCandidates } from './simulator-candidates';

@Component({
  selector: 'app-recommendations',
  templateUrl: './recommendations.component.html',
})
export class RecommendationsComponent {
  readonly source = input<AltitudeCategory>('No Altitude');
  readonly target = input<AltitudeCategory>('Extreme');
  protected readonly insights = inject(AltitudeInsightsService);
  protected readonly data = inject(DataService);
  private readonly ctx = inject(ScoutingContextService);
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly metric = metric;
  protected readonly productText = productText;
  protected readonly labels = ALTITUDE_LABELS;
  readonly result = signal<ApiRecommendationResponse | null>(null);
  readonly pending = signal(false);
  readonly error = signal(false);
  private request = 0;
  readonly candidates = computed(() => {
    const bundle = this.data.bundleOf(this.ctx.pitcherId());
    return bundle && this.data.source() === 'api' ? arsenalCandidates(bundle.arsenal, bundle.pitcher, this.source()) : [];
  });

  constructor() {
    effect(() => {
      this.candidates();
      this.target();
      this.request++;
      this.result.set(null);
      this.error.set(false);
      this.pending.set(false);
    });
    this.destroyRef.onDestroy(() => { this.request++; });
  }

  async compare(): Promise<void> {
    if (!this.candidates().length) return;
    const request = ++this.request;
    this.pending.set(true);
    this.error.set(false);
    this.result.set(null);
    try {
      const result = await this.api.recommendations(this.candidates(), ALTITUDE_TO_API[this.target()]);
      if (request === this.request) this.result.set(result);
    } catch {
      if (request === this.request) this.error.set(true);
    } finally {
      if (request === this.request) this.pending.set(false);
    }
  }
}
