import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { DataService } from '../../core/data-access/data.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { PitcherBundle } from '../../core/models/domain.types';
import { DashboardPage } from './dashboard.page';

describe('Dashboard: rankings con soporte', () => {
  const base = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);
  const pitch = base.pitches[0];
  function bundle(id: string, n: number, score: number | null): PitcherBundle {
    return { ...base, pitcher: { ...base.pitcher, id }, pitches: Array.from({ length: n }, (_, i) =>
      ({ ...pitch, id: `${id}-${i}`, pitcherId: id, stuffPlus: score, season: 2025 })) };
  }
  it('excluye muestras chicas y scores ausentes después de filtrar', () => {
    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideRouter([]),
        { provide: DataService, useValue: {
          source: signal('api'), bundles: signal([bundle('small', 57, 150), bundle('valid', 120, 105), bundle('missing', 200, null)]),
        } },
        { provide: AltitudeInsightsService, useValue: { profile: signal(null), status: signal('idle') } },
      ],
    });
    const fixture = TestBed.createComponent(DashboardPage);
    fixture.detectChanges();
    const page = fixture.componentInstance;
    expect(page.leaders().map((r) => r.pitcher.id)).toEqual(['valid']);
    expect(page.pitchLeaders()[0].n).toBe(177);
    page.filters.set({ ...page.filters(), pitcherId: 'small' });
    fixture.detectChanges();
    expect(page.leaders()).toEqual([]);
    expect(page.pitchLeaders()).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('Ningún lanzador alcanza el mínimo');
    fixture.destroy();
  });
});
