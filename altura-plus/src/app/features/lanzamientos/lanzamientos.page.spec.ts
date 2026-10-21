import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { buildSyntheticBundle, SYNTHETIC_PITCHERS } from '../../core/data-access/synthetic-data';
import { PitcherBundle } from '../../core/models/domain.types';
import { LanzamientosPage } from './lanzamientos.page';
import { PitchEvaluationService, PitchProbabilities } from './pitch-evaluation.service';

describe('Stuff+ final as the primary analysis score', () => {
  const base = buildSyntheticBundle(SYNTHETIC_PITCHERS[0]);
  const pitch = base.pitches[0];
  const bundle: PitcherBundle = {
    ...base,
    pitches: [
      { ...pitch, id: 'a', stuffPlus: 150, pitchingPlus: 150, stuffFinal: 95, finalHistoryStatus: 'regularized_2024_history', finalHistoryN: 200 },
      { ...pitch, id: 'b', stuffPlus: 90, pitchingPlus: 90, stuffFinal: 115, finalHistoryStatus: 'group_prior_only', finalHistoryN: 0 },
      { ...pitch, id: 'c', stuffPlus: 200, pitchingPlus: 200, stuffFinal: null },
      { ...pitch, id: 'd', stuffFinal: NaN },
    ],
  };
  let fixture: ComponentFixture<LanzamientosPage>;
  let component: LanzamientosPage;
  let bundles: ReturnType<typeof signal<readonly PitcherBundle[]>>;

  beforeEach(async () => {
    bundles = signal([bundle]);
    await TestBed.configureTestingModule({
      imports: [LanzamientosPage],
      providers: [
        { provide: DataService, useValue: {
          bundles, source: signal('api'),
          bundleOf: (id: string) => bundles().find((b) => b.pitcher.id === id),
        } },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) } } },
      ],
    }).overrideComponent(LanzamientosPage, {
      set: { providers: [{ provide: PitchEvaluationService, useValue: { evaluate: async () => null } }] },
    }).compileComponents();
    fixture = TestBed.createComponent(LanzamientosPage);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('averages only finite final scores and reports coverage and prior-only history', () => {
    expect(component.finalSummary()).toEqual({ value: 105, n: 2, priorOnly: 1 });
    expect(fixture.nativeElement.querySelector('.final-overview .final-value').textContent).toContain('105.0');
    expect(fixture.nativeElement.querySelector('.score-coverage').textContent).toContain('2 de 4');
  });

  it('sorts by final score, not by the physical or base score, keeping missing scores last', () => {
    expect(component.sortKey()).toBe('final');
    expect(component.sortedPitches().map((p) => p.id)).toEqual(['b', 'a', 'c', 'd']);
    component.setSort('final');
    expect(component.sortedPitches().map((p) => p.id)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('puts the final score ahead of diagnostics in the summary and table', () => {
    const element = fixture.nativeElement as HTMLElement;
    const primary = element.querySelector('.final-overview')!;
    expect(primary.compareDocumentPosition(element.querySelector('.diagnostic-summary')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const header = element.querySelectorAll('thead th')[1];
    expect(header.classList.contains('final-column')).toBeTrue();
    expect(header.getAttribute('aria-sort')).toBe('descending');
    expect(header.textContent).toContain('Experimental');
    expect(element.querySelector('tbody tr .final-column')?.textContent).toContain('115.0');
  });

  it('opens from another column and leads the modal with the final score before diagnostics and maps', async () => {
    (fixture.nativeElement.querySelector('tbody tr td:nth-child(3)') as HTMLElement).click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialog.open).toBeTrue();
    const primary = dialog.querySelector('.final-score')!;
    expect(primary.querySelector('.final-value')?.textContent).toContain('115.0');
    expect(primary.textContent).toContain('Sin historia propia');
    expect(primary.compareDocumentPosition(dialog.querySelector('.diagnostic-stats')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(primary.compareDocumentPosition(dialog.querySelector('.pitch-dialog__charts')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(dialog.querySelectorAll('svg').length).toBe(2);
    component.closeDetail();
    fixture.detectChanges();
  });

  it('never substitutes a physical/base score when final estimates are absent', async () => {
    bundles.set([{ ...bundle, pitches: [{ ...pitch, id: 'missing', stuffPlus: 130, pitchingPlus: 120, stuffFinal: null }] }]);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(component.finalSummary()).toEqual({ value: null, n: 0, priorOnly: 0 });
    expect(fixture.nativeElement.querySelector('.final-overview .final-value strong').textContent.trim()).toBe('\u2014');
    component.openDetail('missing');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('dialog .final-value strong').textContent.trim()).toBe('\u2014');
    expect(fixture.nativeElement.querySelector('dialog .final-score').textContent).toContain('No se sustituye');
    component.closeDetail();
    fixture.detectChanges();
  });

  it('recomputes the summary for the current filters without treating it as a population score', () => {
    component.updateFilters({ ...component.filters(), pitcherId: 'absent' });
    expect(component.finalSummary()).toEqual({ value: null, n: 0, priorOnly: 0 });
    expect(component.pitches().length).toBe(0);
  });

  it('renders exactly eight targets with one final estimate per event, not two probability groups', async () => {
    component.openDetail('b');
    fixture.detectChanges();
    await fixture.whenStable();
    const evaluation: PitchProbabilities = {
      family: 'pitching', whiff: .01, calledStrike: .91, chase: .103,
      weak: .194, hard: .267, groundball: .302, warning: '',
      contactSource: 'Contact proxy', chaseSource: 'Conditional chase', groundballSource: 'Conditional groundball',
      final: {
        status: 'experimental', score: 115, probabilities: { whiff: .015, called_strike: .922 },
        score_version: 'F11', model_id: 'test', history_status: 'group_prior_only',
        history_n: 0, warnings: '', experimental: true,
      },
    };
    component.probabilities.set(evaluation);
    component.probabilityStatus.set('ready');
    fixture.detectChanges();
    const element = fixture.nativeElement.querySelector('.pitch-targets') as HTMLElement;
    expect(element.querySelectorAll('.target-row').length).toBe(8);
    expect(element.querySelectorAll('[data-target="whiff"]').length).toBe(1);
    expect(element.querySelector('[data-target="whiff"] .target-value strong')?.textContent).toBe('1.5%');
    expect(element.querySelector('[data-target="called_strike"] .target-value strong')?.textContent).toBe('92.2%');
    expect(element.querySelector('[data-target="chase"] .target-value strong')?.textContent).toBe('10.3%');
    expect(element.querySelector('[data-target="xRunValue"] .target-value strong')?.textContent).toBe('No disponible');
    expect(element.querySelector('[data-target="out_within_pa"] .target-value strong')?.textContent).toBe('No disponible');
    expect(element.textContent).not.toContain('91.0%');
    expect(element.textContent).not.toContain('Probabilidades de referencia');
    expect(element.querySelector('.target-method')?.hasAttribute('open')).toBeFalse();
    component.closeDetail();
    fixture.detectChanges();
  });

  it('shows unavailable target values instead of filling them with zero or base scores', () => {
    expect(component.targetRows().length).toBe(8);
    expect(component.targetRows().every((t) => component.targetValue(t) === 'No disponible')).toBeTrue();
    expect(component.targetValue({ ...component.targetRows()[0], value: 0 })).toBe('0.0%');
  });

  it('groups the summary and targets separately and keeps an accessible close header outside the content grid', async () => {
    component.openDetail('b');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    const header = dialog.querySelector('.pitch-dialog__head') as HTMLElement;
    const layout = dialog.querySelector('.pitch-dialog__layout')!;
    const summary = layout.querySelector('.pitch-dialog__summary')!;
    expect(dialog.getAttribute('aria-labelledby')).toBe('pitch-detail');
    expect(layout.children.length).toBe(2);
    expect(summary.querySelector('.final-score')).not.toBeNull();
    expect(summary.querySelectorAll('svg').length).toBe(2);
    expect(layout.children[1].classList.contains('pitch-targets')).toBeTrue();
    expect(layout.contains(header)).toBeFalse();
    expect(getComputedStyle(header).position).toBe('sticky');
    (header.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(component.detailOpen()).toBeFalse();
    expect(dialog.open).toBeFalse();
  });
});
