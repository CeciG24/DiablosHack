import { TestBed } from '@angular/core/testing';
import { MovementChartComponent } from './movement-chart.component';
import { StrikeZoneComponent } from './strike-zone.component';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';

describe('Selección accesible en mapas de lanzamientos', () => {
  const pitches = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]).pitches.slice(0, 3);

  it('sincroniza clic y teclado en movimiento sin modificar las físicas', () => {
    const fixture = TestBed.createComponent(MovementChartComponent);
    fixture.componentRef.setInput('pitches', pitches);
    fixture.componentRef.setInput('interactive', true);
    fixture.componentRef.setInput('highlightIndex', 0);
    fixture.detectChanges();
    const selected: string[] = [];
    fixture.componentInstance.pitchSelected.subscribe((id) => selected.push(id));
    fixture.nativeElement.querySelectorAll('.mv__dot')[2].dispatchEvent(new MouseEvent('click'));
    fixture.nativeElement.querySelector('svg').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    expect(selected).toEqual([pitches[2].id, pitches[2].id]);
    expect(fixture.componentInstance.points()[0].ivbIn).toBe(pitches[0].ivbIn);
    fixture.destroy();
  });

  it('recorre solo ubicaciones visibles y no selecciona en modo estático', () => {
    const fixture = TestBed.createComponent(StrikeZoneComponent);
    fixture.componentRef.setInput('pitches', [pitches[0], { ...pitches[1], plateXIn: 100 }, pitches[2]]);
    fixture.componentRef.setInput('selectedId', pitches[0].id);
    fixture.componentRef.setInput('interactive', true);
    fixture.detectChanges();
    const selected: string[] = [];
    fixture.componentInstance.pitchSelected.subscribe((id) => selected.push(id));
    fixture.nativeElement.querySelector('svg').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    expect(selected).toEqual([pitches[2].id]);
    fixture.componentRef.setInput('interactive', false);
    fixture.componentInstance.selectPitch(pitches[0].id);
    expect(selected.length).toBe(1);
    fixture.destroy();
  });
});
