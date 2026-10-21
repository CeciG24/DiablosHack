import { Component, computed, input, output } from '@angular/core';
import { PitchScore } from '../../core/models/domain.types';
import { PITCH_COLORS } from './movement-chart.component';

@Component({
  selector: 'app-strike-zone',
  template: `
    <svg viewBox="0 0 340 300" [attr.role]="interactive() ? 'group' : 'img'" [attr.tabindex]="interactive() ? 0 : null"
      [attr.aria-label]="'Ubicación de ' + pitches().length + ' pitches, vista del catcher' + (interactive() ? '. Selecciona un punto o usa las flechas izquierda y derecha.' : '')"
      (keydown.arrowright)="stepSelection(1, $event)" (keydown.arrowleft)="stepSelection(-1, $event)" class="zone">
      <rect x="20" y="10" width="300" height="260" rx="8" fill="var(--bg)" />
      <rect [attr.x]="x(-8.5)" [attr.y]="y(44)" [attr.width]="x(8.5) - x(-8.5)" [attr.height]="y(18) - y(44)" fill="var(--tile)" stroke="var(--ink)" />
      @for (v of [-2.83, 2.83]; track v) {
        <line [attr.x1]="x(v)" [attr.x2]="x(v)" [attr.y1]="y(44)" [attr.y2]="y(18)" stroke="var(--line)" />
      }
      @for (v of [26.67, 35.33]; track v) {
        <line [attr.x1]="x(-8.5)" [attr.x2]="x(8.5)" [attr.y1]="y(v)" [attr.y2]="y(v)" stroke="var(--line)" />
      }
      @for (p of points(); track p.id) {
        <circle [attr.cx]="x(p.plateXIn)" [attr.cy]="y(p.plateZIn)" [attr.r]="p.id === selectedId() ? 6 : 3.2"
          [attr.fill]="colors[p.pitchType]" [attr.stroke]="p.id === selectedId() ? 'var(--ink)' : 'none'" stroke-width="2" opacity="0.75"
          [style.cursor]="interactive() ? 'pointer' : 'default'" (click)="selectPitch(p.id)">
          <title>{{ p.pitchType }} · X {{ p.plateXIn.toFixed(1) }} · Z {{ p.plateZIn.toFixed(1) }} in</title>
        </circle>
      }
      <path d="M151 277 H189 V285 L170 296 L151 285 Z" fill="var(--tile)" stroke="var(--muted)" />
      <text x="27" y="27">Altura (in)</text>
      <text x="315" y="290" text-anchor="end">Horizontal (in)</text>
    </svg>
    @if (points().length < pitches().length) {
      <p class="note">{{ pitches().length - points().length }} ubicaciones fuera del rango visible (X ±24 in; Z 0–60 in).</p>
    }
  `,
  styles: `.zone { width: 100%; max-height: 320px; } text { fill: var(--muted); font: 11px 'IBM Plex Sans', sans-serif; }`,
})
export class StrikeZoneComponent {
  readonly interactive = input(false);
  readonly pitchSelected = output<string>();
  readonly pitches = input<readonly PitchScore[]>([]);
  readonly selectedId = input<string | null>(null);
  protected readonly colors = PITCH_COLORS;
  readonly points = computed(() => this.pitches().filter((p) =>
    Number.isFinite(p.plateXIn) && Number.isFinite(p.plateZIn) &&
    Math.abs(p.plateXIn) <= 24 && p.plateZIn >= 0 && p.plateZIn <= 60));
  x(value: number): number { return 170 + value * 6.25; }
  y(value: number): number { return 270 - value * (260 / 60); }
  selectPitch(id: string): void {
    if (this.interactive()) this.pitchSelected.emit(id);
  }
  stepSelection(direction: number, event: Event): void {
    const points = this.points();
    if (!this.interactive() || !points.length) return;
    event.preventDefault();
    const current = points.findIndex((p) => p.id === this.selectedId());
    this.selectPitch(points[(current + direction + points.length) % points.length].id);
  }
}
