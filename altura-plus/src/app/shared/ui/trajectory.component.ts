import { UpperCasePipe } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';

export interface TrajectoryInput {
  veloMph: number;
  ivbIn: number;
  hbIn: number;
  plateXIn: number;
  plateZIn: number;
}

export type TrajectoryView = 'side' | 'top' | 'catcher' | 'pitcher';

const W = 380;
const H = 240;
const CX = W / 2;

interface P3 { x: number; y: number; z: number }

/**
 * Trayectoria con 4 cámaras estilo referencia Rapsodo.
 * Modelo: release a 54 ft / z=66 in; cruce en (plateX, plateZ) in.
 * Cada vista es una proyección 2D de la misma curva.
 */
@Component({
  selector: 'app-trajectory',
  imports: [UpperCasePipe],
  template: `
    <div class="tj-wrap">
      <div class="tj-views" role="group" aria-label="Ángulo de cámara">
        @for (v of views; track v) {
          <button type="button" [class.is-active]="view() === v" (click)="view.set(v)">
            {{ v | uppercase }}
          </button>
        }
      </div>
      <svg [attr.viewBox]="'0 0 ' + w + ' ' + h" class="tj" role="img"
           [attr.aria-label]="'Trayectoria del pitch, vista ' + view()">
        <!-- escenario por vista -->
        @switch (view()) {
          @case ('catcher') {
            <rect x="0" y="0" [attr.width]="w" [attr.height]="h" class="tj__sky" />
            <rect x="0" [attr.y]="h * 0.62" [attr.width]="w" [attr.height]="h * 0.16" class="tj__wall" />
            <rect x="0" [attr.y]="h * 0.78" [attr.width]="w" [attr.height]="h * 0.22" class="tj__grass" />
            <ellipse [attr.cx]="cx" [attr.cy]="h * 0.9" rx="90" ry="16" class="tj__dirt" />
            <!-- cajas de bateo -->
            <rect [attr.x]="cx - 52" [attr.y]="h * 0.84" width="30" height="34" class="tj__box" />
            <rect [attr.x]="cx + 22" [attr.y]="h * 0.84" width="30" height="34" class="tj__box" />
            <polygon points="190,206 200,218 190,230 180,218" class="tj__plate" />
            <!-- zona de strike: esquinas físicas (±8.3in, 18-44in) proyectadas -->
            <g class="tj__zone">
              <rect [attr.x]="zoneBox().x" [attr.y]="zoneBox().y"
                    [attr.width]="zoneBox().w" [attr.height]="zoneBox().h" />
              <line [attr.x1]="zoneBox().x" [attr.y1]="zoneBox().y + zoneBox().h / 3"
                    [attr.x2]="zoneBox().x + zoneBox().w" [attr.y2]="zoneBox().y + zoneBox().h / 3" />
              <line [attr.x1]="zoneBox().x" [attr.y1]="zoneBox().y + zoneBox().h * 2 / 3"
                    [attr.x2]="zoneBox().x + zoneBox().w" [attr.y2]="zoneBox().y + zoneBox().h * 2 / 3" />
              <line [attr.x1]="zoneBox().x + zoneBox().w / 3" [attr.y1]="zoneBox().y"
                    [attr.x2]="zoneBox().x + zoneBox().w / 3" [attr.y2]="zoneBox().y + zoneBox().h" />
              <line [attr.x1]="zoneBox().x + zoneBox().w * 2 / 3" [attr.y1]="zoneBox().y"
                    [attr.x2]="zoneBox().x + zoneBox().w * 2 / 3" [attr.y2]="zoneBox().y + zoneBox().h" />
            </g>
          }
          @case ('pitcher') {
            <rect x="0" y="0" [attr.width]="w" [attr.height]="h" class="tj__sky" />
            @for (d of [10, 20, 30, 40, 50]; track d) {
              <line [attr.x1]="cx - d * 4.2" [attr.y1]="h - 26 - d * 2.4"
                    [attr.x2]="cx + d * 4.2" [attr.y2]="h - 26 - d * 2.4" class="tj__depth" />
            }
            <ellipse [attr.cx]="cx" [attr.cy]="h - 26 - 54 * 2.4" rx="24" ry="6" class="tj__dirt" />
            <g class="tj__zone">
              <rect [attr.x]="zoneBox().x" [attr.y]="zoneBox().y"
                    [attr.width]="zoneBox().w" [attr.height]="zoneBox().h" />
              <line [attr.x1]="zoneBox().x" [attr.y1]="zoneBox().y + zoneBox().h / 3"
                    [attr.x2]="zoneBox().x + zoneBox().w" [attr.y2]="zoneBox().y + zoneBox().h / 3" />
              <line [attr.x1]="zoneBox().x" [attr.y1]="zoneBox().y + zoneBox().h * 2 / 3"
                    [attr.x2]="zoneBox().x + zoneBox().w" [attr.y2]="zoneBox().y + zoneBox().h * 2 / 3" />
              <line [attr.x1]="zoneBox().x + zoneBox().w / 3" [attr.y1]="zoneBox().y"
                    [attr.x2]="zoneBox().x + zoneBox().w / 3" [attr.y2]="zoneBox().y + zoneBox().h" />
              <line [attr.x1]="zoneBox().x + zoneBox().w * 2 / 3" [attr.y1]="zoneBox().y"
                    [attr.x2]="zoneBox().x + zoneBox().w * 2 / 3" [attr.y2]="zoneBox().y + zoneBox().h" />
            </g>
          }
          @case ('side') {
            <rect x="0" y="0" [attr.width]="w" [attr.height]="h" class="tj__sky" />
            <line x1="14" [attr.y1]="h - 26" [attr.x2]="w - 14" [attr.y2]="h - 26" class="tj__ground" />
            <rect x="20" [attr.y]="h - 34" width="30" height="8" rx="3" class="tj__mound2" />
            <rect [attr.x]="zoneBox().x" [attr.y]="h - 34" width="16" height="8" class="tj__plate" />
            <rect [attr.x]="zoneBox().x" [attr.y]="zoneBox().y"
                  [attr.width]="zoneBox().w" [attr.height]="zoneBox().h" class="tj__zone-side" />
            <text x="24" y="18" class="tj__cap">montículo</text>
            <text [attr.x]="zoneBox().x - 8" [attr.y]="zoneBox().y - 8" class="tj__cap">zona (in)</text>
          }
          @case ('top') {
            <rect x="0" y="0" [attr.width]="w" [attr.height]="h" class="tj__sky" />
            <ellipse [attr.cx]="cx" [attr.cy]="26" rx="16" ry="6" class="tj__mound2" />
            <polygon points="190,210 199,202 199,214 190,220 181,214 181,202" class="tj__plate" />
            <line [attr.x1]="cx - 100" [attr.y1]="218" [attr.x2]="cx" [attr.y2]="26" class="tj__foul" />
            <line [attr.x1]="cx + 100" [attr.y1]="218" [attr.x2]="cx" [attr.y2]="26" class="tj__foul" />
            <line [attr.x1]="cx" [attr.y1]="218" [attr.x2]="cx" [attr.y2]="26" class="tj__depth" />
            <rect [attr.x]="zoneBox().x" [attr.y]="zoneBox().y"
                  [attr.width]="zoneBox().w" [attr.height]="zoneBox().h" class="tj__zone-side" />
            <text x="16" y="20" class="tj__cap">HB (in) →</text>
          }
        }

        <!-- trayectoria -->
        <path [attr.d]="pathD()" class="tj__path" [style.stroke]="color()" />
        <circle [attr.cx]="end()[0]" [attr.cy]="end()[1]" r="5" class="tj__ball" [style.fill]="color()" />

        <text x="12" [attr.y]="h - 8" class="tj__cap">{{ caption() }}</text>
      </svg>
      <div class="tj-readout" role="status">
        <span>Cruce en plato: X {{ pitch().plateXIn.toFixed(1) }} in · Z {{ pitch().plateZIn.toFixed(1) }} in</span>
        <strong [class.tj-readout--outside]="!inZone()">{{ inZone() ? 'En zona' : 'Fuera de zona' }}</strong>
      </div>
    </div>
  `,
  styles: `
    .tj-wrap { position: relative; }
    .tj { width: 100%; height: auto; display: block; }
    .tj-readout {
      display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px;
      padding: 6px 8px; font-size: 0.88rem; color: var(--ink);
    }
    .tj-readout strong { color: var(--green-mx); }
    .tj-readout .tj-readout--outside { color: var(--red); }
    .tj-views {
      position: absolute; top: 6px; right: 6px; z-index: 2;
      display: flex; flex-direction: column; gap: 4px;
      button {
        min-width: 86px; border: 1px solid var(--line); border-radius: 6px;
        background: rgba(255, 255, 255, 0.9); color: var(--muted);
        font-family: var(--font-display); font-size: 0.78rem; font-weight: 700;
        letter-spacing: 0.08em; padding: 5px 8px; cursor: pointer;
        transition: all 160ms ease;
        &.is-active { background: var(--red); border-color: var(--red); color: #fff; }
        &:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }
      }
    }
    .tj__sky { fill: #f7f8fa; }
    .tj__grass { fill: #a9c98f; }
    .tj__wall { fill: #d5d7dc; }
    .tj__dirt { fill: #d8c9a8; }
    .tj__mound2 { fill: #b9bcc4; }
    .tj__plate { fill: #fff; stroke: var(--muted); stroke-width: 1.2; }
    .tj__box { fill: none; stroke: #fff; stroke-width: 1.6; opacity: 0.9; }
    .tj__foul { stroke: #fff; stroke-width: 1.6; opacity: 0.9; }
    .tj__depth { stroke: #c4c7cd; stroke-width: 1; stroke-dasharray: 3 4; }
    .tj__ground { stroke: var(--muted); stroke-width: 1.4; }
    .tj__zone rect { fill: rgba(208, 20, 44, 0.05); stroke: var(--ink); stroke-width: 1.4; }
    .tj__zone line { stroke: var(--ink); stroke-width: 0.9; opacity: 0.6; }
    .tj__zone-side { fill: rgba(208, 20, 44, 0.05); stroke: var(--red); stroke-width: 1.4; stroke-dasharray: 5 3; }
    .tj__path { fill: none; stroke-width: 2.8; stroke-linecap: round; }
    .tj__ball { stroke: #fff; stroke-width: 1.5; }
    .tj__cap { font-size: 12px; fill: var(--muted); font-weight: 600; }
  `,
})
export class TrajectoryComponent {
  readonly pitch = input.required<TrajectoryInput>();
  readonly color = input('var(--red)');
  readonly caption = input('');

  readonly view = signal<TrajectoryView>('catcher');
  readonly views: TrajectoryView[] = ['side', 'top', 'catcher', 'pitcher'];
  readonly w = W;
  readonly h = H;
  readonly cx = CX;

  /**
   * Curva 3D: y = profundidad en ft (54 -> 0), x/z en pulgadas.
   * Marco absoluto del catcher en x (+ = derecha del catcher): igual que
   * `hbIn`/`plateXIn` en los datos, sin espejado por mano.
   */
  private path3d = computed<P3[]>(() => {
    const p = this.pitch();
    const pts: P3[] = [];
    const N = 40;
    for (let i = 0; i <= N; i++) {
      const t = i / N;
      pts.push({
        y: 54 * (1 - t),
        x: (p.hbIn / 2) * Math.sin(Math.PI * t) + p.plateXIn * t * t,
        z: 66 + (p.plateZIn - 66) * t + p.ivbIn * Math.sin(Math.PI * t) * 0.55,
      });
    }
    return pts;
  });

  private project(p: P3): [number, number] {
    switch (this.view()) {
      case 'side': // profundidad horizontal, altura vertical
        return [30 + (54 - p.y) * 5.6, H - 26 - p.z * 1.55];
      case 'top': // HB horizontal, profundidad vertical
        return [CX + p.x * 2.0, 210 - p.y * 3.4];
      case 'catcher': // detrás del plato: perspectiva simple hacia el montículo
      {
        const k = 1 - p.y / 90;
        return [CX + p.x * 2.1 * k, H - 22 - p.y * 1.2 - p.z * 1.5 * k];
      }
      case 'pitcher': // detrás del pitcher hacia el plato
      default:
        return [CX + p.x * 1.9, H - 26 - p.y * 2.4 - p.z * 1.0];
    }
  }

  readonly pathD = computed(() => {
    const pts = this.path3d().map((p) => this.project(p));
    return 'M ' + pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ');
  });

  readonly end = computed<[number, number]>(() =>
    this.project(this.path3d()[this.path3d().length - 1]),
  );

  readonly inZone = computed(() => {
    const { plateXIn, plateZIn } = this.pitch();
    return Math.abs(plateXIn) <= 8.3 && plateZIn >= 18 && plateZIn <= 44;
  });

  /**
   * Rectángulo de la zona de strike proyectado con la misma cámara que la
   * trayectoria: límites físicos x=±8.3 in, z=18..44 in en el plano del plato.
   */
  readonly zoneBox = computed(() => {
    switch (this.view()) {
      case 'side': {
        // la zona es un plano vertical en la profundidad del plato
        const [px] = this.project({ x: 0, y: 0, z: 0 });
        const [, yTop] = this.project({ x: 0, y: 0, z: 44 });
        const [, yBot] = this.project({ x: 0, y: 0, z: 18 });
        return { x: px - 8, y: yTop, w: 16, h: yBot - yTop };
      }
      case 'top': {
        const [xl] = this.project({ x: -8.3, y: 0, z: 0 });
        const [xr] = this.project({ x: 8.3, y: 0, z: 0 });
        const [, plateY] = this.project({ x: 0, y: 0, z: 0 });
        return { x: xl, y: plateY - 5, w: xr - xl, h: 10 };
      }
      default: {
        const [x0, y0] = this.project({ x: -8.3, y: 0, z: 44 });
        const [x1, y1] = this.project({ x: 8.3, y: 0, z: 18 });
        return {
          x: Math.min(x0, x1),
          y: Math.min(y0, y1),
          w: Math.abs(x1 - x0),
          h: Math.abs(y1 - y0),
        };
      }
    }
  });
}
