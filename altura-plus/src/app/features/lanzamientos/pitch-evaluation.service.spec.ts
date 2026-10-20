import { TestBed } from '@angular/core/testing';
import { ApiService } from '../../core/api/api.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { PitchEvaluationService, PitchProbabilities, pitchTargetRows } from './pitch-evaluation.service';

const EVALUATION: PitchProbabilities = {
  family: 'pitching', whiff: .01, calledStrike: .91, chase: .103,
  weak: .194, hard: .267, groundball: .302, warning: '',
  contactSource: 'Contacto auxiliar validado.',
  groundballSource: 'Rodado auxiliar validado.',
  chaseSource: 'Chase auxiliar validado.',
  final: {
    status: 'experimental', score: 120, probabilities: { whiff: .015, called_strike: .922 },
    model_id: 'fixture', score_version: 'F11', history_status: 'regularized_2024_history',
    history_n: 200, warnings: '', experimental: true,
  },
};

describe('Una estimacion por target', () => {
  it('prefiere los eventos finales y conserva auxiliares sin promediar ni duplicar valores', () => {
    const targets = pitchTargetRows(EVALUATION);
    expect(targets.map((t) => t.id)).toEqual([
      'whiff', 'chase', 'called_strike', 'weak_contact', 'groundball', 'hard_contact', 'xRunValue', 'out_within_pa',
    ]);
    expect(new Set(targets.map((t) => t.id)).size).toBe(8);
    expect(targets.find((t) => t.id === 'whiff')?.value).toBe(.015);
    expect(targets.find((t) => t.id === 'called_strike')?.value).toBe(.922);
    expect(targets.find((t) => t.id === 'chase')?.value).toBe(.103);
    expect(targets.find((t) => t.id === 'hard_contact')?.value).toBe(.267);
    expect(targets.find((t) => t.id === 'whiff')?.source).toContain('con arsenal');
    expect(targets.find((t) => t.id === 'chase')?.source).toContain('sin arsenal');
  });

  it('mantiene denominadores, proxies y targets no implementados explicitos', () => {
    const targets = pitchTargetRows(EVALUATION);
    expect(targets.find((t) => t.id === 'whiff')?.denominator).toContain('No incluye foul');
    expect(targets.find((t) => t.id === 'chase')?.denominator).toContain('fuera de la zona');
    expect(targets.find((t) => t.id === 'groundball')?.denominator).toContain('entra en juego');
    expect(targets.find((t) => t.id === 'hard_contact')?.detail).toContain('No es una probabilidad');
    expect(targets.find((t) => t.id === 'xRunValue')?.format).toBe('runs');
    expect(targets.find((t) => t.id === 'xRunValue')?.value).toBeNull();
    expect(targets.find((t) => t.id === 'out_within_pa')?.value).toBeNull();
  });

  it('usa una referencia base explicita solo cuando el modelo final no esta disponible', () => {
    const targets = pitchTargetRows({ ...EVALUATION, final: null });
    expect(targets.find((t) => t.id === 'whiff')?.value).toBe(.01);
    expect(targets.find((t) => t.id === 'called_strike')?.value).toBe(.91);
    expect(targets.find((t) => t.id === 'whiff')?.source).toContain('Base');
    expect(targets.find((t) => t.id === 'whiff')?.detail).toContain('no est');
    const partial = pitchTargetRows({
      ...EVALUATION, final: { ...EVALUATION.final!, probabilities: { called_strike: .922 } },
    });
    expect(partial.find((t) => t.id === 'whiff')?.value).toBeNull();
  });

  it('conserva ceros reales y rechaza probabilidades invalidas sin fabricar targets', () => {
    const targets = pitchTargetRows({
      ...EVALUATION, weak: NaN, hard: 2,
      final: { ...EVALUATION.final!, probabilities: { whiff: 0, called_strike: Infinity } },
    });
    expect(targets.find((t) => t.id === 'whiff')?.value).toBe(0);
    expect(targets.find((t) => t.id === 'called_strike')?.value).toBeNull();
    expect(targets.find((t) => t.id === 'weak_contact')?.value).toBeNull();
    expect(targets.find((t) => t.id === 'hard_contact')?.value).toBeNull();
    expect(pitchTargetRows(null).every((t) => t.value === null)).toBeTrue();
  });
});

describe('Evaluación individual de un pitch', () => {
  const pitch = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]).pitches[0];
  const api = jasmine.createSpyObj<ApiService>('ApiService', ['predict', 'finalScore']);

  beforeEach(() => {
    api.predict.calls.reset();
    api.finalScore.calls.reset();
    api.finalScore.and.resolveTo({ records: [] });
    TestBed.configureTestingModule({
      providers: [PitchEvaluationService, { provide: ApiService, useValue: api }],
    });
  });

  it('no pide probabilidades con físicas incompletas o sintéticas', async () => {
    expect(await TestBed.inject(PitchEvaluationService).evaluate(pitch, 'R')).toBeNull();
    expect(api.predict).not.toHaveBeenCalled();
    expect(api.finalScore).not.toHaveBeenCalled();
  });

  it('respeta los denominadores y conserva nulos de las cabezas condicionales', async () => {
    api.predict.and.resolveTo({
      release_id: 'test', records: [{ stuff: {
        status: 'ok', score: 100, warnings: 'F8 provisional', provisional: true, score_version: 'private',
        probabilities: { whiff: 0.14 },
        conditional_probabilities: { weak_contact_proxy_bip: null, groundball_bip: 0.45 },
        contact_route: 'smoothed_training_prevalence', contact_status: 'experimental',
        groundball_route: 'model', groundball_status: 'validated',
      } }],
    });
    const result = await TestBed.inject(PitchEvaluationService).evaluate({
      ...pitch, apiPitchType: 'Four-Seam', spinAxisSin: 0, spinAxisCos: 1,
      extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 2,
    }, 'R');
    expect(api.predict.calls.mostRecent().args[1]).toBe('stuff');
    expect(result?.whiff).toBe(0.14);
    expect(result?.weak).toBeNull();
    expect(result?.groundball).toBe(0.45);
    expect(result?.warning).not.toContain('F8');
    expect(result?.contactSource).toContain('no es una predicción individual');
    expect(result?.groundballSource).toContain('validado');
    expect(result?.final).toBeNull();
    expect(api.finalScore).not.toHaveBeenCalled();
  });

  it('envia fisicas, ubicacion, conteo e ID para recuperar el arsenal sin mezclar F8 y F11', async () => {
    api.predict.and.resolveTo({
      release_id: 'test', records: [{ pitching: {
        status: 'ok', score: 104, warnings: '', provisional: true, score_version: 'F8',
        probabilities: { whiff: .14, called_strike: .1 },
        conditional_probabilities: { hard_contact_bip: .3 },
      } }],
    });
    const final = {
      status: 'experimental' as const, score: 108, probabilities: { whiff: .25, called_strike: .2 },
      model_id: 'fixture', score_version: 'F11', experimental: true, warnings: '',
      history_status: 'regularized_2024_history' as const, history_n: 150,
    };
    api.finalScore.and.resolveTo({ records: [final] });
    const result = await TestBed.inject(PitchEvaluationService).evaluate({
      ...pitch, apiPitchType: 'Four-Seam', spinAxisSin: 0, spinAxisCos: 1,
      extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 2,
      balls: 1, strikes: 2, batterSide: 'L', plateXIn: 6, plateZIn: 30,
    }, 'R');
    expect(api.predict.calls.mostRecent().args[1]).toBe('pitching');
    const record = api.finalScore.calls.mostRecent().args[0][0];
    expect(record).toEqual(jasmine.objectContaining({
      pitcher_anon_id: pitch.pitcherId, plate_loc_side: .5, plate_loc_height: 2.5,
      balls: 1, strikes: 2, batter_side: 'Left',
    }));
    expect(result?.final?.score).toBe(108);
    expect(result?.final?.history_n).toBe(150);
    expect(result?.whiff).toBe(.14);
    expect(result?.final?.probabilities?.['whiff']).toBe(.25);
  });

  it('no presenta el score F8 como final cuando F11 falla', async () => {
    api.predict.and.resolveTo({
      release_id: 'test', records: [{ pitching: {
        status: 'ok', score: 104, warnings: '', provisional: true, score_version: 'F8',
      } }],
    });
    api.finalScore.and.rejectWith(new Error('503'));
    const result = await TestBed.inject(PitchEvaluationService).evaluate({
      ...pitch, apiPitchType: 'Four-Seam', spinAxisSin: 0, spinAxisCos: 1,
      extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 2,
      balls: 0, strikes: 0, batterSide: 'R',
    }, 'R');
    expect(result?.family).toBe('pitching');
    expect(result?.final).toBeNull();
  });

  it('conserva el modelo final aunque falle el servicio auxiliar', async () => {
    api.predict.and.rejectWith(new Error('503'));
    api.finalScore.and.resolveTo({ records: [EVALUATION.final!] });
    const result = await TestBed.inject(PitchEvaluationService).evaluate({
      ...pitch, apiPitchType: 'Four-Seam', spinAxisSin: 0, spinAxisCos: 1,
      extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 2,
      balls: 0, strikes: 0, batterSide: 'R',
    }, 'R');
    const targets = pitchTargetRows(result);
    expect(targets.find((t) => t.id === 'whiff')?.value).toBe(.015);
    expect(targets.find((t) => t.id === 'chase')?.value).toBeNull();
    expect(result?.final?.score).toBe(120);
  });

  it('informa error de consulta cuando ambos servicios fallan', async () => {
    api.predict.and.rejectWith(new Error('503'));
    api.finalScore.and.rejectWith(new Error('503'));
    await expectAsync(TestBed.inject(PitchEvaluationService).evaluate({
      ...pitch, apiPitchType: 'Four-Seam', spinAxisSin: 0, spinAxisCos: 1,
      extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 2,
      balls: 0, strikes: 0, batterSide: 'R',
    }, 'R')).toBeRejectedWithError('No se pudieron consultar los modelos del lanzamiento.');
  });
});
