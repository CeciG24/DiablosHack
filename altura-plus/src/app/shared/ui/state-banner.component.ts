import { Component, input, output } from '@angular/core';

/** Estados obligatorios: carga, error recuperable, sin datos, OOD, insuficiente. */
@Component({
  selector: 'app-state-banner',
  template: `
    <div class="state state--{{ kind() }}" role="status">
      <span class="state__icon" aria-hidden="true">{{ icon() }}</span>
      <div class="state__text">
        <strong>{{ title() }}</strong>
        @if (detail()) { <p>{{ detail() }}</p> }
      </div>
      @if (kind() === 'error') {
        <button class="state__retry" type="button" (click)="retry.emit()">Reintentar</button>
      }
    </div>
  `,
  styles: `
    .state {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; border-radius: 8px;
      font-size: 0.94rem; border: 1px solid var(--line);
      background: var(--bg); color: var(--ink);
    }
    .state p { margin: 2px 0 0; color: var(--muted); font-size: 0.88rem; }
    .state__icon { font-weight: 800; color: var(--muted); }
    .state--error { border-color: var(--red); background: #fdf2f3; }
    .state--error .state__icon { color: var(--red); }
    .state--warn { border-color: #f59e0b; background: #fef9ec; }
    .state--insufficient { border-color: var(--amber); background: #fef3c7; }
    .state__retry {
      margin-left: auto; border: 1px solid var(--red); color: var(--red);
      background: transparent; border-radius: 6px; padding: 4px 12px;
      font-size: 0.88rem; font-weight: 700; cursor: pointer;
      transition: background 160ms ease;
    }
    .state__retry:hover { background: var(--red); color: #fff; }
    .state__retry:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }
  `,
})
export class StateBannerComponent {
  readonly kind = input.required<'loading' | 'error' | 'empty' | 'warn' | 'insufficient' | 'ood'>();
  readonly title = input.required<string>();
  readonly detail = input<string>();
  readonly retry = output<void>();

  icon(): string {
    switch (this.kind()) {
      case 'loading': return '…';
      case 'error': return '✕';
      case 'empty': return '∅';
      case 'warn': return '△';
      case 'ood': return '⇞';
      default: return '◦';
    }
  }
}
