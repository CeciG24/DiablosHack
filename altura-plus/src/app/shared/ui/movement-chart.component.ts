import { Component, computed, input, output } from '@angular/core';
import { PitchScore, PitchType } from '../../core/models/domain.types';

export interface MovementPoint {
  hbIn: number;
  ivbIn: number;
  pitchType: PitchType;
  stuffPlus?: number | null;
  selected?: boolean;
}

export type MovementColorMode = 'type' | 'stuff';

/** Escala secuencial blanco/rosa -> rojo para Stuff+ predicho (80-120). */
function stuffColor(stuff: number): string {
  const t = Math.min(1, Math.max(0, (stuff - 80) / 40));
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${lerp(240, 208)}, ${lerp(226, 20)}, ${lerp(228, 44)})`;
}

const LIMIT = 24;
const SIZE = 260;
const MID = SIZE / 2;
const SCALE = MID / LIMIT;

/** IVB × HB en pulgadas, visto desde el catcher; espejado por mano del pitcher. */
@Component({
  selector: 'app-movement-chart',
  template: `
    <svg [attr.viewBox]="'0 0 ' + size + ' ' + size" class="mv" [attr.role]="interactive() ? 'group' : 'img'"
         [attr.tabindex]="interactive() ? 0 : null" [attr.aria-label]="ariaLabel() + (interactive() ? '. Selecciona un punto o usa las flechas izquierda y derecha para recorrer los lanzamientos.' : '')"
         (keydown.arrowright)="stepSelection(1, $event)" (keydown.arrowleft)="stepSelection(-1, $event)">
      <rect x="0" y="0" [attr.width]="size" [attr.height]="size" class="mv__bg" rx="8" />
      @for (t of ticks; track t) {
        <line [attr.x1]="x(t)" [attr.y1]="0" [attr.x2]="x(t)" [attr.y2]="size" class="mv__grid" />
        <line [attr.x1]="0" [attr.y1]="y(t)" [attr.x2]="size" [attr.y2]="y(t)" class="mv__grid" />
        <text [attr.x]="x(t)" [attr.y]="size - 6" class="mv__tick" text-anchor="middle">{{ t }}</text>
        <text [attr.x]="8" [attr.y]="y(t) - 4" class="mv__tick">{{ t }}</text>
      }
      <line [attr.x1]="mid" y1="10" [attr.x2]="mid" [attr.y2]="size - 18" class="mv__axis" />
      <line x1="10" [attr.y1]="mid" [attr.x2]="size - 10" [attr.y2]="mid" class="mv__axis" />
      <text [attr.x]="mid + 6" y="18" class="mv__cap">IVB (in)</text>
      <text [attr.x]="size - 8" [attr.y]="mid - 8" class="mv__cap" text-anchor="end">HB (in) · {{ throws() }}</text>

      @for (p of points(); track $index) {
        <circle [attr.cx]="x(p.hbIn)" [attr.cy]="y(p.ivbIn)" r="4"
                [class.mv__dot--sel]="p.selected" class="mv__dot"
                [style.fill]="dotColor(p)" opacity="0.8" [class.mv__dot--interactive]="interactive()"
                (click)="selectPoint($index)">
          <title>{{ p.pitchType }} · HB {{ p.hbIn }} · IVB {{ p.ivbIn }} in · Stuff+ {{ p.stuffPlus ?? 'no disponible' }}</title>
        </circle>
      }
      @if (highlight(); as h) {
        <circle [attr.cx]="x(h.hbIn)" [attr.cy]="y(h.ivbIn)" r="7"
                class="mv__highlight" />
        @if (comparisonPoint(); as target) {
          <line [attr.x1]="x(h.hbIn)" [attr.y1]="y(h.ivbIn)" [attr.x2]="x(target.hbIn * flip())" [attr.y2]="y(target.ivbIn)" stroke="var(--ink)" stroke-dasharray="3 3" />
          <circle [attr.cx]="x(target.hbIn * flip())" [attr.cy]="y(target.ivbIn)" r="7" fill="var(--tile)" stroke="var(--ink)" stroke-width="2">
            <title>Movimiento estimado en destino</title>
          </circle>
        }
      }
    </svg>
  `,
  styles: `
    .mv { width: 100%; height: auto; max-height: 300px; }
    .mv__bg { fill: var(--bg); }
    .mv__grid { stroke: var(--line); stroke-width: 1; }
    .mv__axis { stroke: var(--ink); stroke-width: 1.4; }
    .mv__tick { font-size: 11px; fill: var(--muted); }
    .mv__cap { font-size: 12px; font-weight: 700; fill: var(--muted); letter-spacing: 0.02em; }
    .mv__dot { transition: opacity 160ms ease; }
    .mv__dot--sel { stroke: var(--ink); stroke-width: 1.6; opacity: 1; }
    .mv__highlight { fill: none; stroke: var(--red); stroke-width: 2; pointer-events:none; }
    .mv__dot--interactive { cursor:pointer; }
    .mv__dot--interactive:hover { stroke:var(--ink); stroke-width:2; opacity:1; }
  `,
})
export class MovementChartComponent {
  readonly interactive = input(false);
  readonly pitchSelected = output<string>();
  readonly pitches = input<readonly PitchScore[]>([]);
  readonly highlightIndex = input<number | null>(null);
  readonly throws = input<'R' | 'L'>('R');
  readonly mirrorLefties = input(true);
  /** 'type' colorea por familia; 'stuff' por predicción de Stuff+ (spec §9.3). */
  readonly colorBy = input<MovementColorMode>('type');
  readonly comparisonPoint = input<{ hbIn: number; ivbIn: number } | null>(null);
  readonly flip = computed(() => this.mirrorLefties() && this.throws() === 'L' ? -1 : 1);

  readonly size = SIZE;
  readonly mid = MID;
  readonly ticks = [-20, -10, 0, 10, 20];

  readonly points = computed<MovementPoint[]>(() => {
    const flip = this.mirrorLefties() && this.throws() === 'L' ? -1 : 1;
    return this.pitches().map((p, i) => ({
      hbIn: p.hbIn * flip,
      ivbIn: p.ivbIn,
      pitchType: p.pitchType,
      stuffPlus: p.stuffPlus,
      selected: i === this.highlightIndex(),
    }));
  });

  readonly highlight = computed<MovementPoint | null>(() => {
    const idx = this.highlightIndex();
    return idx === null ? null : (this.points()[idx] ?? null);
  });

  readonly ariaLabel = computed(() =>
    `Movimiento IVB por HB en pulgadas, ${this.pitches().length} pitches`,
  );

  x(v: number): number { return MID + v * SCALE; }
  y(v: number): number { return MID - v * SCALE; }

  selectPoint(index: number): void {
    const pitch = this.pitches()[index];
    if (this.interactive() && pitch) this.pitchSelected.emit(pitch.id);
  }

  stepSelection(direction: number, event: Event): void {
    if (!this.interactive() || !this.pitches().length) return;
    event.preventDefault();
    const current = this.highlightIndex() ?? -1;
    this.selectPoint((current + direction + this.pitches().length) % this.pitches().length);
  }

  dotColor(p: MovementPoint): string {
    if (this.colorBy() === 'stuff' && p.stuffPlus != null && Number.isFinite(p.stuffPlus)) {
      return stuffColor(p.stuffPlus);
    }
    return PITCH_COLORS[p.pitchType] ?? 'var(--muted)';
  }
}

export const PITCH_COLORS: Record<PitchType, string> = {
  FB: '#D0142C',
  CT: '#f97316',
  SI: '#eab308',
  SL: '#2563eb',
  CB: '#7c3aed',
  CH: '#16a34a',
  SP: '#0891b2',
  SW: '#db2777',
};
