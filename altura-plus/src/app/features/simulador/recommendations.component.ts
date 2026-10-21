import { Component, computed, inject, input, output, signal } from '@angular/core';
import { PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { AltitudeCategory, PITCH_TYPE_NAMES, PitchType } from '../../core/models/domain.types';
import { metric, productText } from '../../core/models/pitch-analysis';

/**
 * Perfiles globales de scouting por altitud (evidencia precomputada).
 * El laboratorio ya no depende de un lanzador de referencia: la comparación
 * de candidatos de arsenal individual se retiró junto con la selección de pitcher.
 */
@Component({
  selector: 'app-recommendations',
  templateUrl: './recommendations.component.html',
  styleUrl: './recommendations.component.scss',
})
export class RecommendationsComponent {
  protected readonly insights = inject(AltitudeInsightsService);
  protected readonly metric = metric;
  protected readonly productText = productText;
  readonly pitchType = input<PitchType>('FB');
  readonly source = input<AltitudeCategory>('No Altitude');
  readonly target = input<AltitudeCategory>('Extreme');
  readonly useReference = output<void>();
  readonly showAll = signal(false);
  readonly matchesScenario = computed(() => this.source() === 'No Altitude' && this.target() === 'Extreme');
  readonly cards = computed(() => (this.insights.profile()?.by_pitch_type ?? []).map((row) => {
    const type = (Object.keys(PITCH_TYPE_TO_API) as PitchType[]).find((key) => PITCH_TYPE_TO_API[key] === row.auto_pitch_type);
    return {
      ...row, name: type ? PITCH_TYPE_NAMES[type] : row.auto_pitch_type,
      selected: type === this.pitchType(),
      physical: this.insights.profile()?.prospect_profile.find((p) => p.auto_pitch_type === row.auto_pitch_type),
      action: row.n < 30 ? 'Ampliar la muestra antes de priorizar este perfil.' :
        row.delta_score < -2 ? 'Contrastar este perfil con alternativas en un bullpen de altura.' :
        'Incluir este perfil en la evaluación de repertorios que conservan su valor relativo.',
    };
  }));
  readonly visibleCards = computed(() => this.showAll() ? this.cards() : this.cards().filter((row) => row.selected));
}
