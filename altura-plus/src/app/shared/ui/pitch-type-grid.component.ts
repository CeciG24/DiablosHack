import { Component, input, output } from '@angular/core';
import { PITCH_TYPE_NAMES, PitchType } from '../../core/models/domain.types';
import { PITCH_COLORS } from './movement-chart.component';

export interface PitchTypeCell {
  type: PitchType;
  usagePct: number;
  stuffPlus: number;
  n: number;
}

/** Grid de tipos de pitch: cada botón filtra toda la vista. */
@Component({
  selector: 'app-pitch-type-grid',
  template: `
    <div class="pt" role="group" aria-label="Filtrar por tipo de pitch">
      <button type="button" class="pt__all" [class.pt__cell--active]="selected() === 'ALL'"
              (click)="select.emit('ALL')">
        <span class="pt__name">Todo el arsenal</span>
        <span class="pt__meta">Todos los lanzamientos</span>
      </button>
      @for (c of cells(); track c.type) {
        <button type="button" class="pt__cell" [class.pt__cell--active]="selected() === c.type"
                [attr.aria-pressed]="selected() === c.type"
                [attr.aria-label]="nameOf(c.type) + ', uso ' + c.usagePct + '%, Stuff+ ' + c.stuffPlus"
                (click)="select.emit(c.type)">
          <span class="pt__dot" [style.background]="colorOf(c.type)"></span>
          <span class="pt__name">{{ nameOf(c.type) }}</span>
          <span class="pt__code">{{ c.type }}</span>
          <span class="pt__meta">Uso {{ c.usagePct }}% · Stuff+ {{ c.stuffPlus }}</span>
          @if (c.n < 40) { <span class="pt__low">n bajo</span> }
        </button>
      }
    </div>
  `,
  styles: `
    .pt { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; }
    .pt__cell, .pt__all {
      position: relative;
      display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
      padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px;
      background: var(--bg); cursor: pointer; text-align: left;
      transition: border-color 160ms ease, background 160ms ease;
    }
    .pt__cell:hover, .pt__all:hover { border-color: var(--red); }
    .pt__cell:focus-visible, .pt__all:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }
    .pt__cell--active { border-color: var(--red); background: #fdf2f3; }
    .pt__dot { width: 8px; height: 8px; border-radius: 50%; }
    .pt__name { font-size: 0.9rem; font-weight: 700; color: var(--ink); line-height: 1.25; overflow-wrap: anywhere; }
    .pt__code { font-weight: 600; font-size: 0.78rem; color: var(--muted); }
    .pt__meta { font-size: 0.78rem; color: var(--muted); font-variant-numeric: tabular-nums; }
    .pt__low {
      font-size: 0.68rem; font-weight: 700; text-transform: uppercase; align-self: flex-start;
      color: var(--amber); background: #fef3c7; border-radius: 4px; padding: 1px 5px;
    }
  `,
})
export class PitchTypeGridComponent {
  readonly cells = input.required<readonly PitchTypeCell[]>();
  readonly selected = input<PitchType | 'ALL'>('ALL');
  readonly select = output<PitchType | 'ALL'>();

  colorOf = (t: PitchType) => PITCH_COLORS[t];
  nameOf = (t: PitchType) => PITCH_TYPE_NAMES[t];
}
