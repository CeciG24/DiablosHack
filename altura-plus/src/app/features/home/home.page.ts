import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { TileComponent } from '../../shared/ui/tile.component';

@Component({
  selector: 'app-home-page',
  imports: [RouterLink, TileComponent],
  template: `
    <div class="home">
      <header class="home__hero">
        <img class="home__logo" src="mictlan-logo.png" alt="MICTLAN" />
        <h1>MICTLAN</h1>
        <p>
          Scouting de pitchers de la LMB · 635k pitches · 2024–2026 · anonimizados.
          Compara <strong>categorías de altitud</strong>, nunca estadios nombrados.
        </p>
        <ol class="home__steps">
          <li>Elige un pitcher en la barra superior</li>
          <li>Filtra por tipo de pitch en la ficha</li>
          <li>Compara categorías en el comparador</li>
          <li>Cierra con la ficha de scouting</li>
        </ol>
        <p class="home__warn">
          Ruta A activa: sin <code>stadium_id</code> no hay resultados por estadio.
          <a routerLink="/metodo" class="home__link">Método y glosario →</a>
        </p>
      </header>

      <div class="grid">
        @for (b of data.bundles(); track b.pitcher.id) {
          <app-tile [label]="b.pitcher.throws + 'HP'" class="span-4">
            <h2 class="home__name">{{ b.pitcher.label }}</h2>
            <p class="home__meta">Stuff+ {{ b.stuffPlus.value }} · n={{ b.stuffPlus.n }} pitches</p>
            <a routerLink="/pitcher" class="home__cta" (click)="ctx.selectPitcher(b.pitcher.id)">
              Ver ficha →
            </a>
          </app-tile>
        }
      </div>
    </div>
  `,
  styles: `
    .home { display: flex; flex-direction: column; gap: 18px; }
    .home__hero {
      background: var(--tile); border: 1px solid var(--line); border-radius: 12px;
      padding: 22px 26px; position: relative; overflow: hidden;
      &::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px;
        background: var(--tricolor);
      }
      .home__logo {
        height: 84px; width: auto; border-radius: 10px; margin-bottom: 10px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
      }
      h1 { margin: 0 0 6px; font-size: 1.6rem; letter-spacing: 0.02em; color: var(--ink); }
      p { margin: 0 0 6px; color: var(--ink); font-size: 1rem; line-height: 1.5; max-width: 65ch; }
    }
    .home__steps {
      margin: 10px 0; padding-left: 20px;
      display: flex; flex-wrap: wrap; gap: 4px 26px;
      font-size: 0.95rem; color: var(--muted);
      li::marker { color: var(--red); font-weight: 700; }
    }
    .home__warn {
      color: var(--amber) !important; font-size: 0.92rem !important;
      code { background: #fef3c7; padding: 1px 5px; border-radius: 4px; }
    }
    .home__link { color: var(--red); font-weight: 600; text-decoration: none; &:hover { text-decoration: underline; } }
    .home__name { margin: 0; font-size: 1.05rem; color: var(--ink); }
    .home__meta { margin: 4px 0 12px; font-size: 0.9rem; color: var(--muted); }
    .home__cta {
      font-size: 0.9rem; font-weight: 700; color: var(--red); text-decoration: none;
      &:hover { text-decoration: underline; }
      &:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }
    }
  `,
})
export class HomePage {
  readonly data = inject(DataService);
  readonly ctx = inject(ScoutingContextService);
}
