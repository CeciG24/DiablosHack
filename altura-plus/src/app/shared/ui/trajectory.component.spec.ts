import { TestBed } from '@angular/core/testing';
import { TrajectoryComponent, TrajectoryInput, TrajectoryView } from './trajectory.component';

describe('TrajectoryComponent', () => {
  const pitch: TrajectoryInput = {
    veloMph: 92, ivbIn: 16, hbIn: 18, plateXIn: 0, plateZIn: 30,
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [TrajectoryComponent] }).compileComponents();
  });

  it('termina en las coordenadas del plato aunque HB sea distinto de cero, en las cuatro cámaras', () => {
    const fixture = TestBed.createComponent(TrajectoryComponent);
    fixture.componentRef.setInput('pitch', pitch);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    for (const view of ['catcher', 'pitcher', 'side', 'top'] as TrajectoryView[]) {
      component.view.set(view);
      fixture.detectChanges();
      const [x, y] = component.end();
      expect(x).withContext(view).toBeCloseTo(view === 'side' ? 332.4 : 190, 5);
      expect(x).withContext(view).toBeGreaterThanOrEqual(component.zoneBox().x);
      expect(x).withContext(view).toBeLessThanOrEqual(component.zoneBox().x + component.zoneBox().w);
      expect(y).withContext(view).toBeGreaterThanOrEqual(component.zoneBox().y);
      expect(y).withContext(view).toBeLessThanOrEqual(component.zoneBox().y + component.zoneBox().h);
    }
  });

  it('alinea la zona en vista catcher con la elevación del plato y no con el cielo', () => {
    const fixture = TestBed.createComponent(TrajectoryComponent);
    fixture.componentRef.setInput('pitch', pitch);
    fixture.detectChanges();
    const zone = fixture.componentInstance.zoneBox();
    expect(zone.y + zone.h).toBeGreaterThan(185);
    expect(zone.y + zone.h).toBeLessThan(218);
  });

  it('sitúa fuera del rectángulo un pitch que cruza fuera de la zona', () => {
    const fixture = TestBed.createComponent(TrajectoryComponent);
    fixture.componentRef.setInput('pitch', { ...pitch, plateXIn: 15, plateZIn: 48 });
    fixture.detectChanges();
    for (const view of ['catcher', 'pitcher'] as TrajectoryView[]) {
      fixture.componentInstance.view.set(view);
      fixture.detectChanges();
      const [x, y] = fixture.componentInstance.end();
      const zone = fixture.componentInstance.zoneBox();
      expect(x).withContext(view).toBeGreaterThan(zone.x + zone.w);
      expect(y).withContext(view).toBeLessThan(zone.y);
    }
    expect(fixture.componentInstance.inZone()).toBeFalse();
  });

  it('actualiza el punto de cruce según X/Z sin que HB cambie la coordenada final', () => {
    const fixture = TestBed.createComponent(TrajectoryComponent);
    fixture.componentRef.setInput('pitch', pitch);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const initial = component.end();
    expect(component.inZone()).toBeTrue();

    fixture.componentRef.setInput('pitch', { ...pitch, plateXIn: -10, plateZIn: 16, hbIn: -20 });
    fixture.detectChanges();
    expect(component.end()[0]).toBeCloseTo(190 - 10 * 2.1, 5);
    expect(component.end()[1]).toBeCloseTo(218 - 16 * 1.5, 5);
    expect(component.end()).not.toEqual(initial);
    expect(component.inZone()).toBeFalse();
  });

  it('el IVB negativo también modifica la curvatura sin mover el cruce fijo', () => {
    const fixture = TestBed.createComponent(TrajectoryComponent);
    fixture.componentRef.setInput('pitch', { ...pitch, ivbIn: 16 });
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const before = component.pathD();
    const end = component.end();
    fixture.componentRef.setInput('pitch', { ...pitch, ivbIn: -10 });
    fixture.detectChanges();
    expect(component.pathD()).not.toEqual(before);
    expect(component.end()[0]).toBeCloseTo(end[0], 5);
    expect(component.end()[1]).toBeCloseTo(end[1], 5);
  });
});
