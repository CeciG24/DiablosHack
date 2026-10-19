import { Injectable, inject } from '@angular/core';
import { ApiService } from '../../core/api/api.service';
import { PitchScore } from '../../core/models/domain.types';
import { headDescription, predictionWarnings } from '../../core/models/pitch-analysis';

export interface PitchProbabilities {
  whiff: number | null;
  weak: number | null;
  groundball: number | null;
  warning: string;
  contactSource: string;
  groundballSource: string;
}

@Injectable()
export class PitchEvaluationService {
  private readonly api = inject(ApiService);

  async evaluate(pitch: PitchScore, hand: 'R' | 'L'): Promise<PitchProbabilities | null> {
    const physics = [pitch.veloMph, pitch.spinRpm, pitch.ivbIn, pitch.hbIn,
      pitch.spinAxisSin, pitch.spinAxisCos, pitch.releaseHeightFt, pitch.releaseSideFt, pitch.extensionFt];
    if (!pitch.apiPitchType || physics.some((v) => v == null || !Number.isFinite(v))) return null;
    const result = await this.api.predict([{
      pitch_uid: pitch.id,
      pitcher_anon_id: pitch.pitcherId,
      auto_pitch_type: pitch.apiPitchType,
      pitcher_throws: hand === 'L' ? 'Left' : 'Right',
      rel_speed: pitch.veloMph, spin_rate: pitch.spinRpm,
      spin_axis_sin: pitch.spinAxisSin, spin_axis_cos: pitch.spinAxisCos,
      rel_height: pitch.releaseHeightFt, rel_side: pitch.releaseSideFt, extension: pitch.extensionFt,
      induced_vert_break: pitch.ivbIn, horz_break: pitch.hbIn,
    }], 'stuff');
    const prediction = result.records[0]?.stuff;
    if (!prediction || prediction.status !== 'ok') return null;
    return {
      whiff: prediction.probabilities?.['whiff'] ?? null,
      weak: prediction.conditional_probabilities?.['weak_contact_proxy_bip'] ?? null,
      groundball: prediction.conditional_probabilities?.['groundball_bip'] ?? null,
      warning: predictionWarnings(prediction.warnings),
      contactSource: headDescription(prediction.contact_route, prediction.contact_status),
      groundballSource: headDescription(prediction.groundball_route, prediction.groundball_status),
    };
  }
}
