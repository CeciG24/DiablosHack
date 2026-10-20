import { Component, computed, input } from '@angular/core';
import { PitchScore, PitchType } from '../../core/models/domain.types';

export interface MovementPoint {
  hbIn: number;
  ivbIn: number;
  pitchType: PitchType;
  stuffPlus?: number | null;
  pitchingPlus?: number | null;
  selected?: boolean;
}

export type MovementColorMode = 'type' | 'stuff' | 'pitching';

/** Escala secuencial blanco/rosa -> rojo para scores + (80-120, misma forma 100+10z). */
function scoreColor(score: number): string {
  const t = Math.min(1, Math.max(0, (score - 80) / 40));
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
    <svg [attr.viewBox]="'0 0 ' + size + ' ' + size" class="mv" role="img"
         [attr.aria-label]="ariaLabel()">
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
                [style.fill]="dotColor(p)" opacity="0.8">
          <title>{{ p.pitchType }} · Pitching+ {{ p.pitchingPlus ?? 'no disponible' }} · Stuff+ {{ p.stuffPlus ?? 'no disponible' }}</title>
        </circle>
      }
      @if (extremes(); as ex) {
        @for (i of ex.worst; track i) {
          @if (points()[i]; as p) {
            <circle [attr.cx]="x(p.hbIn)" [attr.cy]="y(p.ivbIn)" r="8" class="mv__extreme mv__extreme--worst">
              <title>Menos efectivo · {{ p.pitchType }} · Pitching+ {{ p.pitchingPlus ?? '—' }}</title>
            </circle>
          }
        }
        @for (i of ex.best; track i) {
          @if (points()[i]; as p) {
            <circle [attr.cx]="x(p.hbIn)" [attr.cy]="y(p.ivbIn)" r="8" class="mv__extreme mv__extreme--best">
              <title>Más efectivo · {{ p.pitchType }} · Pitching+ {{ p.pitchingPlus ?? '—' }}</title>
            </circle>
          }
        }
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
    .mv__extreme { fill: none; stroke-width: 2.2; }
    .mv__extreme--best { stroke: #16a34a; }
    .mv__extreme--worst { stroke: var(--red); stroke-dasharray: 3 2; }
    .mv__highlight { fill: none; stroke: var(--red); stroke-width: 2; }
  `,
})
export class MovementChartComponent {
  readonly pitches = input<readonly PitchScore[]>([]);
  readonly highlightIndex = input<number | null>(null);
  readonly throws = input<'R' | 'L'>('R');
  readonly mirrorLefties = input(true);
  /** 'type' colorea por familia; 'stuff'/'pitching' por el score + correspondiente (spec §9.3). */
  readonly colorBy = input<MovementColorMode>('type');
  readonly comparisonPoint = input<{ hbIn: number; ivbIn: number } | null>(null);
  /** Índices (sobre `pitches`) a marcar explícitamente como más/menos efectivos. */
  readonly extremes = input<{ best: readonly number[]; worst: readonly number[] } | null>(null);
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
      pitchingPlus: p.pitchingPlus,
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

  dotColor(p: MovementPoint): string {
    const mode = this.colorBy();
    const score = mode === 'stuff' ? p.stuffPlus : mode === 'pitching' ? p.pitchingPlus : null;
    if (score != null && Number.isFinite(score)) {
      return scoreColor(score);
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
