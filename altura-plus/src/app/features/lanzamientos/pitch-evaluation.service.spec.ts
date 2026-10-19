import { TestBed } from '@angular/core/testing';
import { ApiService } from '../../core/api/api.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { PitchEvaluationService } from './pitch-evaluation.service';

describe('Evaluación individual de un pitch', () => {
  const pitch = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]).pitches[0];
  const api = jasmine.createSpyObj<ApiService>('ApiService', ['predict']);

  beforeEach(() => {
    api.predict.calls.reset();
    TestBed.configureTestingModule({
      providers: [PitchEvaluationService, { provide: ApiService, useValue: api }],
    });
  });

  it('no pide probabilidades con físicas incompletas o sintéticas', async () => {
    expect(await TestBed.inject(PitchEvaluationService).evaluate(pitch, 'R')).toBeNull();
    expect(api.predict).not.toHaveBeenCalled();
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
  });
});
