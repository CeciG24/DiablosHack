import { Injectable, inject } from '@angular/core';
import { ApiFinalScore, ApiService } from '../../core/api/api.service';
import { PitchScore } from '../../core/models/domain.types';
import { headDescription, predictionWarnings } from '../../core/models/pitch-analysis';

export interface PitchProbabilities {
  /** Familia que produjo las probabilidades: 'pitching' = combinada
   * (física + ubicación + conteo + lado), 'stuff' = solo física. */
  family: 'pitching' | 'stuff';
  whiff: number | null;
  calledStrike: number | null;
  chase: number | null;
  weak: number | null;
  hard: number | null;
  groundball: number | null;
  warning: string;
  contactSource: string;
  groundballSource: string;
  chaseSource: string;
  final: ApiFinalScore | null;
}

export interface PitchTarget {
  id: string;
  symbol: string;
  label: string;
  value: number | null;
  format: 'probability' | 'runs';
  denominator: string;
  source: string;
  detail: string;
}

function probability(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}

/** One estimate per target, with model provenance; never blend model probabilities. */
export function pitchTargetRows(evaluation: PitchProbabilities | null): readonly PitchTarget[] {
  const final = evaluation?.final?.status === 'experimental' ? evaluation.final : null;
  const baseSource = evaluation?.family === 'stuff' ? 'Física pura · sin arsenal' : 'Base · sin arsenal';
  const eventSource = final ? 'Modelo final · con arsenal' : evaluation ? baseSource : 'No disponible';
  const auxiliarySource = evaluation ? 'Auxiliar · sin arsenal' : 'No disponible';
  const fallbackDetail = final ? 'Estimación del modelo final experimental.'
    : evaluation ? 'Referencia sin arsenal: el modelo final no está disponible.'
    : 'Se requiere una evaluación válida del lanzamiento.';
  const event = (key: 'whiff' | 'called_strike') => probability(final
    ? final.probabilities?.[key]
    : key === 'whiff' ? evaluation?.whiff : evaluation?.calledStrike);
  return [
    { id: 'whiff', symbol: 'P(whiff)', label: 'Swing en blanco', value: event('whiff'),
      format: 'probability', denominator: 'Por lanzamiento. No incluye foul.',
      source: eventSource, detail: fallbackDetail },
    { id: 'chase', symbol: 'P(chase)', label: 'Swing fuera de zona',
      value: probability(evaluation?.chase), format: 'probability',
      denominator: 'Solo entre lanzamientos fuera de la zona.',
      source: auxiliarySource, detail: evaluation?.chaseSource ?? 'No hay estimación auxiliar disponible.' },
    { id: 'called_strike', symbol: 'P(called_strike)', label: 'Strike cantado',
      value: event('called_strike'), format: 'probability', denominator: 'Por lanzamiento.',
      source: eventSource, detail: fallbackDetail },
    { id: 'weak_contact', symbol: 'P(weak_contact)', label: 'Contacto débil · proxy',
      value: probability(evaluation?.weak), format: 'probability',
      denominator: 'Solo cuando la pelota entra en juego.',
      source: auxiliarySource, detail: evaluation?.contactSource ?? 'No hay estimación auxiliar disponible.' },
    { id: 'groundball', symbol: 'P(groundball)', label: 'Rodado',
      value: probability(evaluation?.groundball), format: 'probability',
      denominator: 'Solo cuando la pelota entra en juego.',
      source: auxiliarySource, detail: evaluation?.groundballSource ?? 'No hay estimación auxiliar disponible.' },
    { id: 'hard_contact', symbol: 'P(hard_contact)', label: 'Contacto duro · proxy',
      value: probability(evaluation?.hard), format: 'probability',
      denominator: 'Solo cuando la pelota entra en juego.',
      source: auxiliarySource, detail: 'No es una probabilidad de barril (barrel). ' +
        (evaluation?.contactSource ?? 'No hay estimación auxiliar disponible.') },
    { id: 'xRunValue', symbol: 'xRunValue', label: 'Carreras esperadas', value: null,
      format: 'runs', denominator: 'Valor esperado de carreras; no es un porcentaje.',
      source: 'No disponible', detail: 'Esta versión no tiene un objetivo de carreras validado ni un modelo xRunValue.' },
    { id: 'out_within_pa', symbol: 'P(out within PA)', label: 'Out en la aparición al plato', value: null,
      format: 'probability', denominator: 'Por aparición al plato (PA), no por lanzamiento.',
      source: 'No disponible', detail: 'Esta versión no tiene un modelo entrenado para este target.' },
  ];
}

@Injectable()
export class PitchEvaluationService {
  private readonly api = inject(ApiService);

  async evaluate(pitch: PitchScore, hand: 'R' | 'L'): Promise<PitchProbabilities | null> {
    const physics = [pitch.veloMph, pitch.spinRpm, pitch.ivbIn, pitch.hbIn,
      pitch.spinAxisSin, pitch.spinAxisCos, pitch.releaseHeightFt, pitch.releaseSideFt, pitch.extensionFt];
    if (!pitch.apiPitchType || physics.some((v) => v == null || !Number.isFinite(v))) return null;
    const base = {
      pitch_uid: pitch.id,
      pitcher_anon_id: pitch.pitcherId,
      auto_pitch_type: pitch.apiPitchType,
      pitcher_throws: hand === 'L' ? 'Left' : 'Right',
      rel_speed: pitch.veloMph, spin_rate: pitch.spinRpm,
      spin_axis_sin: pitch.spinAxisSin, spin_axis_cos: pitch.spinAxisCos,
      rel_height: pitch.releaseHeightFt, rel_side: pitch.releaseSideFt, extension: pitch.extensionFt,
      induced_vert_break: pitch.ivbIn, horz_break: pitch.hbIn,
    };
    // Modelo combinado sólo si el registro trae el contexto completo
    // (conteo, lado del bateador, ubicación en la zona).
    const hasContext = pitch.balls != null && Number.isInteger(pitch.balls) && pitch.balls >= 0 && pitch.balls <= 3 &&
      pitch.strikes != null && Number.isInteger(pitch.strikes) && pitch.strikes >= 0 && pitch.strikes <= 2 &&
      (pitch.batterSide === 'L' || pitch.batterSide === 'R') &&
      Number.isFinite(pitch.plateXIn) && Number.isFinite(pitch.plateZIn);
    const record = hasContext
      ? { ...base, plate_loc_height: pitch.plateZIn / 12, plate_loc_side: pitch.plateXIn / 12,
          balls: pitch.balls, strikes: pitch.strikes,
          batter_side: pitch.batterSide === 'L' ? 'Left' : 'Right' }
      : base;
    const family = hasContext ? 'pitching' as const : 'stuff' as const;
    const [result, finalResult] = await Promise.all([
      this.api.predict([record], family).catch(() => null),
      hasContext ? this.api.finalScore([record]).catch(() => null) : Promise.resolve(null),
    ]);
    if (!result && !finalResult) throw new Error('No se pudieron consultar los modelos del lanzamiento.');
    const basePrediction = result?.records[0]?.[family];
    const prediction = basePrediction?.status === 'ok' ? basePrediction : null;
    const final = finalResult?.records[0]?.status === 'experimental' ? finalResult.records[0] : null;
    if (!prediction && !final) return null;
    return {
      family,
      whiff: prediction?.probabilities?.['whiff'] ?? null,
      calledStrike: prediction?.probabilities?.['called_strike'] ?? null,
      chase: prediction?.p_chase_given_outside ?? null,
      weak: prediction?.conditional_probabilities?.['weak_contact_proxy_bip'] ?? null,
      hard: prediction?.conditional_probabilities?.['hard_contact_bip'] ?? null,
      groundball: prediction?.conditional_probabilities?.['groundball_bip'] ?? null,
      warning: predictionWarnings([prediction?.warnings, final?.warnings].filter(Boolean).join(';')),
      contactSource: headDescription(prediction?.contact_route, prediction?.contact_status),
      groundballSource: headDescription(prediction?.groundball_route, prediction?.groundball_status),
      chaseSource: headDescription(prediction?.chase_route, prediction?.chase_status),
      final,
    };
  }
}
