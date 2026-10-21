import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { ApiService } from '../../core/api/api.service';
import { DataService } from '../../core/data-access/data.service';
import { ProfilerEvaluation, ProfilerPayload, ProfilerReference } from '../../core/models/profiler.types';
import { PerfiladorPage } from './perfilador.page';
import { autoMapping, importCandidate, readImport, templateCsv } from './profiler-import';

function result(payload: ProfilerPayload): ProfilerEvaluation {
  const summary = { source_score: 100, target_score: 97, paired_source_score: 100, delta: -3,
    coverage: 1, weight: 100, supported_weight: 100, entries: 2, observed_n: 180, interval: null };
  return { mode: payload.mode, target: payload.target, release_id: 'fixture', representative: payload.mode === 'profiles',
    arsenal_in_model: false, summary, groups: [{ ...summary, auto_pitch_type: 'Four-Seam' }],
    records: payload.entries.map((e) => ({ key: e.key, auto_pitch_type: e.pitch['auto_pitch_type'] as string,
      source: 'No Altitude', weight: e.weight, source_score: 100, target_score: 97, delta: -3,
      target_ivb: 10, target_hb: 5, status: 'experimental', reason: null, warnings: '' })) };
}

describe('Perfilador de candidatos', () => {
  let api: jasmine.SpyObj<ApiService>;
  let setItem: jasmine.Spy;
  const table = readImport(templateCsv('profiles'));
  const candidate = () => importCandidate(table, autoMapping(table.headers),
    { mode: 'profiles', hand: 'Right', category: 'No Altitude', speed: 'mph', movement: 'in', release: 'ft' });
  beforeEach(() => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['profilerReference', 'evaluateCandidate']);
    api.profilerReference.and.resolveTo({ years: [2025, 2026], hand: 'Right', data_run: 'fixture',
      raw_n: 0, complete_n: 0, excluded_n: 0, by_year: {}, groups: [], points: [] } satisfies ProfilerReference);
    api.evaluateCandidate.and.callFake(async (payload) => result(payload));
    spyOn(Storage.prototype, 'getItem').and.returnValue('[]');
    setItem = spyOn(Storage.prototype, 'setItem').and.stub();
    TestBed.configureTestingModule({
      imports: [PerfiladorPage],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: DataService, useValue: { bundles: signal([]), status: signal('loading'), source: signal(null), bundleOf: () => undefined } },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) } } },
      ],
    });
  });
  it('abre sin esperar la carga global y no inventa scores para el formulario vacío', async () => {
    const fixture = TestBed.createComponent(PerfiladorPage);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('Perfilador');
    expect(fixture.componentInstance.problems().length).toBeGreaterThan(0);
    await fixture.componentInstance.evaluate();
    expect(api.evaluateCandidate).not.toHaveBeenCalled();
    expect(fixture.componentInstance.snapshot()).toBeNull();
    fixture.destroy();
  });
  it('evalúa, conserva el original y marca el resultado anterior como desactualizado', async () => {
    const fixture = TestBed.createComponent(PerfiladorPage);
    const page = fixture.componentInstance;
    page.setCandidate(candidate()); fixture.detectChanges(); await fixture.whenStable();
    await page.evaluate(); fixture.detectChanges();
    expect(page.fresh()).toBeTrue();
    expect(page.snapshot()?.result.summary.delta).toBe(-3);
    expect(page.mapPitches().find((p) => p.pitcherId === 'candidate')?.stuffPlus).toBe(100);
    page.updateRow(page.candidate().rows[0].key, 'veloMph', 100);
    fixture.detectChanges();
    expect(page.stale()).toBeTrue();
    expect(page.mapPitches().find((p) => p.pitcherId === 'candidate')?.stuffPlus).toBeNull();
    expect(page.snapshot()?.candidate.rows[0].veloMph).toBe(93);
    page.restoreOriginal();
    expect(page.candidate().rows[0].veloMph).toBe(93);
    fixture.destroy();
  });
  it('descarta respuestas obsoletas cuando se edita durante la inferencia', async () => {
    let resolve!: (value: ProfilerEvaluation) => void;
    let sent!: ProfilerPayload;
    api.evaluateCandidate.and.callFake((payload) => { sent = payload; return new Promise((r) => { resolve = r; }); });
    const fixture = TestBed.createComponent(PerfiladorPage), page = fixture.componentInstance;
    page.setCandidate(candidate()); fixture.detectChanges();
    const evaluation = page.evaluate();
    page.target.set('Medium');
    resolve(result(sent)); await evaluation;
    expect(page.snapshot()).toBeNull();
    expect(page.message()).toContain('cambió durante el cálculo');
    expect(page.busy()).toBeFalse();
    fixture.destroy();
  });
  it('guarda decisiones locales sin adjuntar una evaluación vieja como vigente', async () => {
    const fixture = TestBed.createComponent(PerfiladorPage), page = fixture.componentInstance;
    page.setCandidate(candidate()); fixture.detectChanges(); await page.evaluate();
    page.pin(); expect(page.pins().length).toBe(1);
    page.notes.set('Comprobar el movimiento en bullpen.');
    page.target.set('Medium'); page.saveCase();
    const saved = JSON.parse(setItem.calls.mostRecent().args[1])[0];
    expect(saved.notes).toContain('bullpen');
    expect(saved.evaluation).toBeNull();
    expect(saved.original.rows[0].veloMph).toBe(93);
    page.loadCase(saved);
    expect(page.snapshot()).toBeNull();
    fixture.destroy();
  });
  it('mantiene el trabajo si el navegador no permite guardar y ofrece exportación', () => {
    setItem.and.throwError('quota');
    const fixture = TestBed.createComponent(PerfiladorPage), page = fixture.componentInstance;
    page.setCandidate(candidate()); page.saveCase();
    expect(page.error()).toBe('quota');
    expect(page.saved().length).toBe(0);
    expect(page.candidate().rows.length).toBe(2);
    fixture.destroy();
  });
});
