import { signal } from '@angular/core';
import { TestBed, fakeAsync, flushMicrotasks, tick } from '@angular/core/testing';
import { ApiPredictResponse, ApiService, ApiSimulateResponse } from '../../core/api/api.service';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { DataService } from '../../core/data-access/data.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { SimuladorPage } from './simulador.page';

describe('Simulador: scores y peticiones pendientes', () => {
  const bundle = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);
  let api: jasmine.SpyObj<ApiService>;

  beforeEach(() => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['health', 'predict', 'simulate', 'recommendations']);
    api.health.and.resolveTo(false);
    api.predict.and.resolveTo({ release_id: 'test', records: [] });
    api.simulate.and.resolveTo({ records: [], experimental: true });
    TestBed.configureTestingModule({
      imports: [SimuladorPage],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: DataService, useValue: {
          source: signal('api'), bundles: signal([bundle]), examples: signal([]),
          bundleOf: () => bundle, reload: jasmine.createSpy('reload'),
        } },
        { provide: AltitudeInsightsService, useValue: { profile: signal(null), status: signal('idle') } },
      ],
    });
    TestBed.inject(ScoutingContextService).selectPitcher(bundle.pitcher.id);
  });

  it('no fabrica scores cuando el backend no entrega estimaciones', fakeAsync(() => {
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges();
    tick(600);
    flushMicrotasks();
    expect(fixture.componentInstance.stuffPlus()).toBeNull();
    expect(fixture.componentInstance.locationPlus()).toBeNull();
    expect(fixture.componentInstance.pitchingPlus()).toBeNull();
    fixture.destroy();
  }));

  it('descarta una respuesta anterior cuando los nuevos controles son inválidos', fakeAsync(() => {
    let resolvePrediction: (value: ApiPredictResponse) => void = () => undefined;
    let resolveSimulation: (value: ApiSimulateResponse) => void = () => undefined;
    api.predict.and.returnValue(new Promise((resolve) => { resolvePrediction = resolve; }));
    api.simulate.and.returnValue(new Promise((resolve) => { resolveSimulation = resolve; }));
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges();
    tick(600);
    fixture.componentInstance.set('veloMph', 200);
    fixture.detectChanges();
    resolvePrediction({ release_id: 'old', records: [{ stuff: {
      status: 'ok', score: 125, warnings: '', score_version: 'private', provisional: true,
    } }] });
    resolveSimulation({ records: [], experimental: true });
    flushMicrotasks();
    expect(fixture.componentInstance.live()).toBeNull();
    expect(fixture.componentInstance.apiPending()).toBeFalse();
    fixture.destroy();
  }));

  it('cancela el debounce al salir de la pantalla', fakeAsync(() => {
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges();
    fixture.destroy();
    tick(1000);
    expect(api.predict).not.toHaveBeenCalled();
    expect(api.simulate).not.toHaveBeenCalled();
  }));
});
