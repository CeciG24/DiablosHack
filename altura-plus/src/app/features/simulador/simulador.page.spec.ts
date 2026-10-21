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

  it('muestra xRV en carreras y conserva el cero del baseline', fakeAsync(() => {
    api.predict.and.resolveTo({ release_id: 'test', records: [{ pitching: {
      status: 'ok', score: 100, warnings: '', score_version: 'frozen', provisional: true,
      xrv: { status: 'ok', version: 'xrv_external_lmb2024_v1', reference_label: 'LMB 2024', league: 'LMB', season: 2024, runs_per_pitch: -.0123,
        runs_per_100: -1.23, baseline_runs_per_pitch: 0, delta_vs_count_baseline: -.0123 },
    } }] });
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges();
    tick(600);
    flushMicrotasks();
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('-0.0123');
    expect(content).toContain('-1.23');
    expect(content).toContain('0.0000');
    expect(content).toContain('LMB 2024');
    expect(content).toContain('Menor es mejor');
    fixture.destroy();
  }));

  it('compara Stuff+ físico, no el índice F10, y el titular no depende de Pitching+', fakeAsync(() => {
    api.predict.and.resolveTo({ release_id: 'test', records: [{
      stuff: { status: 'ok', score: 104, warnings: '', score_version: 'F8', provisional: true },
      pitching: { status: 'ok', score: 120, warnings: '', score_version: 'F8', provisional: true },
    }] });
    api.simulate.and.resolveTo({ experimental: true, records: [{
      status: 'experimental', reason: null, source_score: 102, target_score: 97, delta_score: -5,
      target_ivb: 11, target_hb: -6, scope: '', score_version: 'F10',
      stuff_comparison: { status: 'experimental', source_score: 104, target_score: 101, delta_score: -3,
        interval: null, interval_reason: 'individual_uncertainty_not_estimated', release_id: 'test',
        score_version: 'F8', warnings: '', method: 'F8_stuff_on_F10_projected_movement' },
    }] });
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges(); tick(600); flushMicrotasks(); fixture.detectChanges();
    const c = fixture.componentInstance;
    expect(c.targetStuff()).toBe(101);
    expect(c.stuffDelta()).toBe(-3);
    expect(fixture.nativeElement.querySelector('.sim__takeaway h2').textContent).toContain('promedio');
    expect(fixture.nativeElement.querySelector('.sim__takeaway h2').textContent).not.toContain('elite');
    expect(fixture.nativeElement.querySelector('.sim__change strong').textContent.trim()).toBe('-3.0');
    expect(fixture.nativeElement.querySelector('.sim__comparison').textContent).toContain('Intervalo de confianza individual: no disponible');
    fixture.destroy();
  }));

  it('conserva el escenario anterior al recalcular y marca fallos como desactualizados', fakeAsync(() => {
    api.predict.and.resolveTo({ release_id: 'test', records: [{ stuff: {
      status: 'ok', score: 104, warnings: '', score_version: 'F8', provisional: true,
    } }] });
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges(); tick(600); flushMicrotasks(); fixture.detectChanges();
    api.predict.and.rejectWith(new Error('offline'));
    api.simulate.and.rejectWith(new Error('offline'));
    fixture.componentInstance.set('ivbIn', 20);
    fixture.componentInstance.setSourceCat('Extreme');
    fixture.detectChanges();
    expect(fixture.componentInstance.stuffPlus()).toBe(104);
    expect(fixture.componentInstance.shownInput().ivbIn).toBe(15);
    expect(fixture.componentInstance.live()?.source).toBe('No Altitude');
    expect(fixture.componentInstance.stale()).toBeTrue();
    tick(600); flushMicrotasks(); fixture.detectChanges();
    expect(fixture.componentInstance.stuffPlus()).toBe(104);
    expect(fixture.componentInstance.stale()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Resultados desactualizados');
    fixture.componentInstance.set('veloMph', 200);
    fixture.detectChanges();
    expect(fixture.componentInstance.live()).toBeNull();
    fixture.destroy();
  }));

  it('nunca usa el índice F10 como fallback del Stuff+ en destino', fakeAsync(() => {
    api.simulate.and.resolveTo({ experimental: true, records: [{
      status: 'experimental', reason: null, source_score: 102, target_score: 97, delta_score: -5,
      target_ivb: 11, target_hb: -6, scope: '', score_version: 'F10',
    }] });
    const fixture = TestBed.createComponent(SimuladorPage);
    fixture.detectChanges(); tick(600); flushMicrotasks(); fixture.detectChanges();
    expect(fixture.componentInstance.targetStuff()).toBeNull();
    expect(fixture.componentInstance.stuffDelta()).toBeNull();
    fixture.destroy();
  }));
});
