import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';
import { ApiService } from './core/api/api.service';
import { DataService } from './core/data-access/data.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from './core/data-access/synthetic-data';
import { ScoutingContextService } from './core/state/scouting-context.service';

describe('Los cuatro módulos de MICTLAN', () => {
  const bundle = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: DataService, useValue: {
          bundles: signal([bundle]), source: signal('synthetic'), examples: signal([]),
          status: signal('ready'), bundleOf: (id: string) => id === bundle.pitcher.id ? bundle : undefined,
        } },
        { provide: ApiService, useValue: { health: jasmine.createSpy('health').and.resolveTo(false) } },
      ],
    });
    TestBed.inject(ScoutingContextService).selectPitcher(bundle.pitcher.id);
  });

  it('abre Dashboard por defecto y conserva enlaces antiguos con redirecciones', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');
    expect(TestBed.inject(Router).url).toBe('/dashboard');
    await harness.navigateByUrl('/comparador');
    expect(TestBed.inject(Router).url).toBe('/lanzadores');
    await harness.navigateByUrl('/scouting');
    expect(TestBed.inject(Router).url).toBe('/simulador');
  });

  it('renderiza las cuatro vistas sin exponer nombres internos de modelos', async () => {
    const harness = await RouterTestingHarness.create();
    for (const [path, heading] of [
      ['/dashboard', 'El pulso del pitcheo'],
      ['/lanzamientos', 'Análisis de lanzamientos'],
      ['/lanzadores', 'Lanzadores y arsenales'],
      ['/simulador', 'Laboratorio de pitch'],
    ]) {
      await harness.navigateByUrl(path);
      expect(harness.routeNativeElement?.querySelector('h1')?.textContent).toBe(heading);
      expect(harness.routeNativeElement?.textContent).not.toMatch(/\bF(?:8|9|10)\b/);
    }
  });

  it('muestra el estado vacío al filtrar un lanzador que no está en la muestra', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/lanzamientos?pitcher=desconocido');
    expect(harness.routeNativeElement?.textContent).toContain('No hay lanzamientos con estos filtros');
  });
});
