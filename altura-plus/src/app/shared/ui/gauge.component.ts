import { Component, computed, input } from '@angular/core';

/**
 * Anillo tipo Rapsodo para scores (escala ~60–140) o métricas arbitrarias.
 * Anillo rojo por defecto; color secundario para no confundir los tres scores.
 */
@Component({
  selector: 'app-gauge',
  template: `
    @if (!modelAvailable()) {
      <div class="gauge__missing" role="status">Score no disponible</div>
    } @else {
      <div class="gauge" [attr.role]="'img'" [attr.aria-label]="ariaText()">
        <svg viewBox="0 0 120 120" class="gauge__svg" aria-hidden="true">
          <circle cx="60" cy="60" [attr.r]="R" class="gauge__track" />
          <circle
            cx="60" cy="60" [attr.r]="R"
            class="gauge__arc"
            [style.stroke]="accent()"
            [attr.stroke-dasharray]="circumference"
            [attr.stroke-dashoffset]="dashOffset()"
          />
          <text x="60" y="58" text-anchor="middle" class="gauge__value">{{ displayValue() }}</text>
          <text x="60" y="76" text-anchor="middle" class="gauge__unit">{{ unit() }}</text>
        </svg>
        <div class="gauge__stats">
          <span>REF <strong>{{ avg() }}</strong></span>
          @if (maxStat() !== undefined) { <span>MAX <strong>{{ maxStat() }}</strong></span> }
        </div>
      </div>
    }
  `,
  styles: `
    .gauge { display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1; justify-content: center; }
    .gauge__svg { width: 132px; height: 132px; }
    .gauge__track { fill: none; stroke: var(--line); stroke-width: 9; }
    .gauge__arc {
      fill: none; stroke-width: 9; stroke-linecap: round;
      transform: rotate(-90deg); transform-origin: 60px 60px;
      transition: stroke-dashoffset 220ms ease;
    }
    .gauge__value { font-size: 30px; font-weight: 800; fill: var(--ink); }
    .gauge__unit { font-size: 14px; font-weight: 600; fill: var(--muted); letter-spacing: 0.03em; }
    .gauge__stats { display: flex; gap: 16px; font-size: 0.84rem; color: var(--muted); }
    .gauge__stats strong { color: var(--ink); font-size: 0.9rem; }
    .gauge__missing {
      flex: 1; display: flex; align-items: center; justify-content: center;
      color: var(--muted); font-size: 0.9rem; font-weight: 600;
      border: 1px dashed var(--line); border-radius: 8px; min-height: 120px;
    }
  `,
})
export class GaugeComponent {
  readonly value = input.required<number>();
  readonly min = input(60);
  readonly max = input(140);
  readonly avg = input.required<string | number>();
  readonly maxStat = input<string | number>();
  readonly unit = input('pts');
  readonly accent = input('var(--red)');
  readonly title = input('');
  readonly modelAvailable = input(true);
  readonly decimals = input(0);

  readonly R = 50;
  readonly circumference = 2 * Math.PI * this.R;

  readonly dashOffset = computed(() => {
    const span = this.max() - this.min();
    const frac = Math.min(1, Math.max(0, (this.value() - this.min()) / span));
    return this.circumference * (1 - frac);
  });

  readonly displayValue = computed(() => this.value().toFixed(this.decimals()));

  readonly ariaText = computed(
    () => `${this.title()}: ${this.displayValue()} ${this.unit()}`,
  );
}
