import { Component, input } from '@angular/core';

/** Tile blanco reutilizable: encabezado con etiqueta + contenido proyectado. */
@Component({
  selector: 'app-tile',
  template: `
    <section class="tile" [class.tile--wide]="wide()" [attr.aria-label]="label()">
      <header class="tile__head">
        <span class="tile__label">{{ label() }}</span>
        @if (tag()) {
          <span class="tile__tag" [class.tile__tag--warn]="tagTone() === 'warn'">{{ tag() }}</span>
        }
      </header>
      <div class="tile__body">
        <ng-content />
      </div>
    </section>
  `,
  styles: `
    .tile {
      background: var(--tile);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      min-height: 0;
      box-shadow: 0 1px 3px rgba(26, 28, 32, 0.05);
      transition: box-shadow 180ms ease, border-color 180ms ease, transform 180ms ease;
    }
    .tile:hover {
      box-shadow: 0 8px 22px rgba(26, 28, 32, 0.09);
      transform: translateY(-1px);
    }
    .tile:focus-within { border-color: var(--red); }
    .tile__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .tile__label {
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .tile__tag {
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      background: var(--bg);
      border-radius: 999px;
      padding: 2px 8px;
    }
    .tile__tag--warn { color: var(--amber); background: #fef3c7; }
    .tile__body { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  `,
})
export class TileComponent {
  readonly label = input.required<string>();
  readonly tag = input<string>();
  readonly tagTone = input<'neutral' | 'warn'>('neutral');
  readonly wide = input(false);
}
