import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ApiProfile } from '../../core/api/api.service';
import { AltitudeInsightsService } from '../../core/data-access/altitude-insights.service';
import { RecommendationsComponent } from './recommendations.component';

describe('Perfiles de scouting: evidencia, no receta individual', () => {
  const profile: ApiProfile = {
    pair_focus: 'No Altitude -> Extreme Altitude', n_simulated: 30, global_delta_hard_contact_bip_pp: 1,
    scope: 'experimental', prospect_profile: [], caveats: ['Muestra descriptiva.'],
    answers: { q1_ganan_en_altura: '', q2_pierden_en_altura: '', q3_perfil_prospecto: '' },
    by_pitch_type: [
      { auto_pitch_type: 'Four-Seam', n: 100, delta_score: -6, delta_ivb_in: -3, delta_hb_in: -1,
        delta_hard_contact_bip_pp: 1, delta_groundball_bip_pp: 2 },
      { auto_pitch_type: 'Cutter', n: 17, delta_score: .7, delta_ivb_in: -1, delta_hb_in: .1,
        delta_hard_contact_bip_pp: .2, delta_groundball_bip_pp: 1 },
    ],
  };
  it('destaca el tipo editado sin transformar las cifras para otro trayecto', () => {
    TestBed.configureTestingModule({
      imports: [RecommendationsComponent],
      providers: [{ provide: AltitudeInsightsService, useValue: { profile: signal(profile), status: signal('ready') } }],
    });
    const fixture = TestBed.createComponent(RecommendationsComponent);
    fixture.componentRef.setInput('pitchType', 'CT');
    fixture.componentRef.setInput('source', 'Extreme');
    fixture.componentRef.setInput('target', 'No Altitude');
    fixture.detectChanges();
    expect(fixture.componentInstance.matchesScenario()).toBeFalse();
    expect(fixture.componentInstance.visibleCards().length).toBe(1);
    expect(fixture.componentInstance.visibleCards()[0].delta_score).toBe(.7);
    expect(fixture.nativeElement.textContent).toContain('no corresponden al trayecto seleccionado');
    expect(fixture.nativeElement.querySelector('.recommendation__action').textContent).toContain('Ampliar la muestra');
    fixture.componentInstance.showAll.set(true); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.recommendation').length).toBe(2);
    fixture.destroy();
  });
});
