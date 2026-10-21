import { Component, computed, input, output, signal } from '@angular/core';
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

/** Value colors are independent from brand and pitch-type colors. */
function scoreColor(score: number): string {
  if (score >= 110) return 'var(--value-positive)';
  if (score <= 90) return 'var(--value-negative)';
  return 'var(--value-neutral)';
}

const SIZE = 360;
const MID = SIZE / 2;

/** IVB × HB en pulgadas, visto desde el catcher; espejado por mano del pitcher. */
@Component({
  selector: 'app-movement-chart',
  template: `
    <svg [attr.viewBox]="'0 0 ' + size + ' ' + size" class="mv" [attr.role]="canInspect() ? 'group' : 'img'"
         [attr.tabindex]="canInspect() ? 0 : null" [attr.aria-label]="ariaLabel() + (canInspect() ? '. Usa las flechas izquierda y derecha para recorrer los lanzamientos.' : '')"
         (keydown.arrowright)="stepSelection(1, $event)" (keydown.arrowleft)="stepSelection(-1, $event)">
      <rect x="0" y="0" [attr.width]="size" [attr.height]="size" class="mv__bg" />
      @for (t of ticks(); track t) {
        <line [attr.x1]="x(t)" y1="28" [attr.x2]="x(t)" [attr.y2]="size - 34" class="mv__grid" />
        <line x1="30" [attr.y1]="y(t)" [attr.x2]="size - 24" [attr.y2]="y(t)" class="mv__grid" />
        <text [attr.x]="x(t)" [attr.y]="size - 21" class="mv__tick" text-anchor="middle">{{ t }}</text>
        <text x="6" [attr.y]="y(t) + 4" class="mv__tick">{{ t }}</text>
      }
      <line [attr.x1]="mid" y1="28" [attr.x2]="mid" [attr.y2]="size - 34" class="mv__axis" />
      <line x1="30" [attr.y1]="mid" [attr.x2]="size - 24" [attr.y2]="mid" class="mv__axis" />
      <text [attr.x]="mid" y="18" class="mv__cap" text-anchor="middle">IVB (pulgadas)</text>
      <text x="30" [attr.y]="size - 5" class="mv__cap">{{ leftLabel() }}</text>
      <text [attr.x]="size - 24" [attr.y]="size - 5" class="mv__cap" text-anchor="end">{{ rightLabel() }}</text>
      @for (link of connections(); track $index) {
        @if (points()[link.from]; as from) {
          @if (points()[link.to]; as to) {
            <line [attr.x1]="x(from.hbIn)" [attr.y1]="y(from.ivbIn)" [attr.x2]="x(to.hbIn)" [attr.y2]="y(to.ivbIn)" stroke="var(--muted)" stroke-dasharray="2 4" />
          }
        }
      }

      @for (p of points(); track $index) {
        <circle [attr.cx]="x(p.hbIn)" [attr.cy]="y(p.ivbIn)" r="4"
                [class.mv__dot--sel]="p.selected" class="mv__dot"
                [style.fill]="dotColor(p)" opacity="0.55" [class.mv__dot--interactive]="canInspect()"
                (mouseenter)="inspect($index)"
                (click)="selectPoint($index)">
          <title>{{ p.pitchType }} · HB {{ p.hbIn }} · IVB {{ p.ivbIn }} in · Pitching+ {{ p.pitchingPlus ?? 'no disponible' }} · Stuff+ {{ p.stuffPlus ?? 'no disponible' }}</title>
        </circle>
      }
      @if (extremes(); as ex) {
        @for (i of ex.worst; track i) {
          @if (points()[i]; as p) {
            <rect [attr.x]="x(p.hbIn) - 6" [attr.y]="y(p.ivbIn) - 6" width="12" height="12" class="mv__extreme mv__extreme--worst">
              <title>Menor score · {{ p.pitchType }} · {{ extremeMetric() === 'stuff' ? 'Stuff+' : 'Pitching+' }} {{ (extremeMetric() === 'stuff' ? p.stuffPlus : p.pitchingPlus) ?? '—' }}</title>
            </rect>
          }
        }
        @for (i of ex.best; track i) {
          @if (points()[i]; as p) {
            <circle [attr.cx]="x(p.hbIn)" [attr.cy]="y(p.ivbIn)" r="8" class="mv__extreme mv__extreme--best">
              <title>Mayor score · {{ p.pitchType }} · {{ extremeMetric() === 'stuff' ? 'Stuff+' : 'Pitching+' }} {{ (extremeMetric() === 'stuff' ? p.stuffPlus : p.pitchingPlus) ?? '—' }}</title>
            </circle>
          }
        }
      }
      @if (highlight(); as h) {
        <path [attr.d]="'M ' + x(h.hbIn) + ' ' + (y(h.ivbIn)-9) + ' l 9 9 -9 9 -9 -9 Z'" class="mv__highlight" />
        @if (comparisonPoint(); as target) {
          <line [attr.x1]="x(h.hbIn)" [attr.y1]="y(h.ivbIn)" [attr.x2]="x(target.hbIn * flip())" [attr.y2]="y(target.ivbIn)" stroke="var(--ink)" stroke-dasharray="3 3" />
          <circle [attr.cx]="x(target.hbIn * flip())" [attr.cy]="y(target.ivbIn)" r="7" fill="var(--tile)" stroke="var(--ink)" stroke-width="2">
            <title>Movimiento estimado en destino</title>
          </circle>
          <path [attr.d]="arrowHead(h, target)" class="mv__arrow" />
        }
      }
      @for (target of comparisonPoints(); track target.index) {
        @if (points()[target.index]; as origin) {
          <line [attr.x1]="x(origin.hbIn)" [attr.y1]="y(origin.ivbIn)" [attr.x2]="x(target.hbIn * flip())" [attr.y2]="y(target.ivbIn)" stroke="var(--ink)" stroke-dasharray="4 3" />
          <circle [attr.cx]="x(target.hbIn * flip())" [attr.cy]="y(target.ivbIn)" r="7" fill="var(--tile)" stroke="var(--ink)" stroke-width="2"><title>Movimiento proyectado de {{ origin.pitchType }}</title></circle>
          <path [attr.d]="arrowHead(origin, target)" class="mv__arrow" />
        }
      }
    </svg>
    @if (canInspect()) {
      <div class="mv__tooltip" role="status" aria-live="polite">
        @if (inspected(); as p) {
          <strong>{{ p.pitchType }} · HB {{ p.hbIn.toFixed(1) }} · IVB {{ p.ivbIn.toFixed(1) }} in</strong>
          <span>Stuff+ {{ p.stuffPlus?.toFixed(1) ?? '—' }} · Pitching+ {{ p.pitchingPlus?.toFixed(1) ?? '—' }}</span>
        } @else { <span>Toca un punto o usa las flechas del teclado para ver su detalle.</span> }
      </div>
    }
  `,
  styles: `
    :host { display:block; min-width:0; }
    .mv { display:block; width: 100%; height: auto; max-height: 420px; }
    .mv__bg { fill: var(--bg); }
    .mv__grid { stroke: var(--line); stroke-width: 1; }
    .mv__axis { stroke: var(--ink); stroke-width: 1.4; }
    .mv__tick { font-size: 12px; fill: var(--muted); }
    .mv__cap { font-size: 12px; font-weight: 700; fill: var(--muted); letter-spacing: 0.02em; }
    .mv__dot { transition: opacity 160ms ease; }
    .mv__dot--sel { stroke: var(--ink); stroke-width: 1.6; opacity: 1; }
    .mv__highlight { fill: var(--tile); stroke: var(--ink); stroke-width: 2.5; pointer-events:none; }
    .mv__dot--interactive { cursor:pointer; }
    .mv__dot--interactive:hover { stroke:var(--ink); stroke-width:2; opacity:1; }
    .mv__extreme { fill: none; stroke-width: 2.2; pointer-events:none; }
    .mv__extreme--best { stroke: var(--value-positive); }
    .mv__extreme--worst { stroke: var(--value-negative); stroke-dasharray: 3 2; }
    .mv__arrow { fill:var(--ink); pointer-events:none; }
    .mv__tooltip { display:grid; gap:4px; min-height:66px; padding:10px 12px; background:var(--bg); font-size:13px; line-height:1.5; }
    .mv__tooltip strong { font-family:inherit; }
    .mv__tooltip span { color:var(--muted); }
  `,
})
export class MovementChartComponent {
  readonly interactive = input(false);
  readonly inspectable = input(false);
  readonly canInspect = computed(() => this.interactive() || this.inspectable());
  readonly mixedHands = input(false);
  readonly inspectedIndex = signal<number | null>(null);
  readonly pitchSelected = output<string>();
  readonly pitches = input<readonly PitchScore[]>([]);
  readonly highlightIndex = input<number | null>(null);
  readonly throws = input<'R' | 'L'>('R');
  readonly mirrorLefties = input(true);
  /** 'type' colorea por familia; 'stuff'/'pitching' por el score + correspondiente (spec §9.3). */
  readonly colorBy = input<MovementColorMode>('type');
  readonly comparisonPoint = input<{ hbIn: number; ivbIn: number } | null>(null);
  readonly comparisonPoints = input<readonly { index: number; hbIn: number; ivbIn: number }[]>([]);
  readonly connections = input<readonly { from: number; to: number }[]>([]);
  /** Índices (sobre `pitches`) a marcar explícitamente como más/menos efectivos. */
  readonly extremes = input<{ best: readonly number[]; worst: readonly number[] } | null>(null);
  readonly extremeMetric = input<'stuff' | 'pitching'>('pitching');
  readonly flip = computed(() => this.mirrorLefties() && this.throws() === 'L' ? -1 : 1);

  readonly size = SIZE;
  readonly mid = MID;
  readonly limit = computed(() => {
    const values = this.points().flatMap((p) => [Math.abs(p.hbIn), Math.abs(p.ivbIn)]);
    const target = this.comparisonPoint();
    if (target) values.push(Math.abs(target.hbIn), Math.abs(target.ivbIn));
    for (const p of this.comparisonPoints()) values.push(Math.abs(p.hbIn), Math.abs(p.ivbIn));
    return Math.max(24, Math.ceil(Math.max(0, ...values.filter(Number.isFinite)) / 10) * 10);
  });
  readonly ticks = computed(() => {
    const k = Math.floor(this.limit() / 10);
    return Array.from({ length: 2*k + 1 }, (_, i) => (i-k)*10);
  });
  // In this dataset right-handers have positive arm-side HB; mirrored lefties do too.
  readonly leftLabel = computed(() => this.mixedHands() ? 'HB negativo' :
    this.flip() === -1 || this.throws() === 'R' ? 'Lado del guante' : 'Lado del brazo');
  readonly rightLabel = computed(() => this.mixedHands() ? 'HB positivo' :
    this.leftLabel() === 'Lado del brazo' ? 'Lado del guante' : 'Lado del brazo');

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
  readonly inspected = computed(() => this.points()[this.inspectedIndex() ?? this.highlightIndex() ?? -1] ?? null);

  readonly ariaLabel = computed(() =>
    `Movimiento IVB por HB en pulgadas, ${this.pitches().length} pitches`,
  );

  x(v: number): number { return MID + v * (MID - 36) / this.limit(); }
  y(v: number): number { return MID - v * (MID - 36) / this.limit(); }

  arrowHead(h: MovementPoint, target: { hbIn: number; ivbIn: number }): string {
    const x = this.x(target.hbIn * this.flip()), y = this.y(target.ivbIn);
    if (Math.hypot(x-this.x(h.hbIn), y-this.y(h.ivbIn)) < 1) return '';
    const angle = Math.atan2(y-this.y(h.ivbIn), x-this.x(h.hbIn));
    const baseX = x - 10*Math.cos(angle), baseY = y - 10*Math.sin(angle);
    return `M ${x} ${y} L ${baseX+4*Math.sin(angle)} ${baseY-4*Math.cos(angle)} L ${baseX-4*Math.sin(angle)} ${baseY+4*Math.cos(angle)} Z`;
  }

  inspect(index: number): void { if (this.canInspect()) this.inspectedIndex.set(index); }

  selectPoint(index: number): void {
    const pitch = this.pitches()[index];
    this.inspect(index);
    if (this.interactive() && pitch) this.pitchSelected.emit(pitch.id);
  }

  stepSelection(direction: number, event: Event): void {
    if (!this.canInspect() || !this.pitches().length) return;
    event.preventDefault();
    const current = this.interactive() ? this.highlightIndex() ?? -1 : this.inspectedIndex() ?? this.highlightIndex() ?? -1;
    this.selectPoint((current + direction + this.pitches().length) % this.pitches().length);
  }

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
  FB: '#4f46a5',
  CT: '#a62379',
  SI: '#64742b',
  SL: '#2563eb',
  CB: '#7c3aed',
  CH: '#16a34a',
  SP: '#0891b2',
  SW: '#db2777',
};
