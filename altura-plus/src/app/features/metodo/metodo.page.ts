import { Component, inject } from '@angular/core';
import { TileComponent } from '../../shared/ui/tile.component';
import { ScoutingContextService } from '../../core/state/scouting-context.service';

/** Panel Método y limitaciones: qué falta, qué es proxy, holdouts y bloqueados. */
@Component({
  selector: 'app-metodo-page',
  imports: [TileComponent],
  template: `
    <div class="mt">
      <h1>Método y limitaciones</h1>

      <div class="grid">
        <app-tile label="Glosario rápido" class="span-12">
          <dl class="mt__glossary">
            <div><dt>Stuff+ físico</dt><dd>Calidad del lanzamiento por su forma: velocidad, spin y movimiento. 100 = promedio.</dd></div>
            <div><dt>Location+</dt><dd>Precisión de la ubicación respecto a la zona de strike. 100 = promedio.</dd></div>
            <div><dt>Pitching+</dt><dd>Combinación de Stuff+ y Location+ en un solo índice.</dd></div>
            <div><dt>IVB / HB</dt><dd>Movimiento vertical y horizontal inducido, en pulgadas, visto desde el catcher.</dd></div>
            <div><dt>Rango probable</dt><dd>Intervalo donde cae la estimación. Más ancho = más duda.</dd></div>
            <div><dt>n</dt><dd>Número de lanzamientos que soportan el dato.</dd></div>
            <div><dt>Régimen</dt><dd>Interpolado = dentro de lo observado · extrapolado = fuera del rango visto · insuficiente = muestra baja.</dd></div>
            <div><dt>Δ (delta)</dt><dd>Diferencia estimada entre dos categorías o escenarios.</dd></div>
          </dl>
        </app-tile>

        <app-tile label="Régimen de evidencia" class="span-6">
          <p>
            El dashboard opera en <strong>Ruta A</strong>: compara
            <strong>categorías de altitud</strong> (<code>Extreme</code>, <code>Medium</code>,
            <code>No Altitude</code>). No existe <code>stadium_id</code> ni altitud en metros en el
            dataset, por lo que <strong>nunca</strong> se nombra un estadio como resultado validado.
          </p>
          <p>
            La <strong>Ruta B</strong> (comparación entre parques identificados, p. ej. Harp Helú)
            solo se habilita cuando hay metadatos de estadio disponibles; en esta demo es simulada.
          </p>
          <p class="mt__flag">Modo actual: {{ ctx.regimeLabel() }}</p>
        </app-tile>

        <app-tile label="Datos faltantes" class="span-6">
          <ul>
            <li><code>stadium_id</code> y altitud en metros por estadio</li>
            <li>Comparables por tipo de pitch (p. ej. pitchers sin baseline de recta)</li>
            <li>Composición de rivales por categoría</li>
          </ul>
        </app-tile>

        <app-tile label="Proxies declarados" class="span-6">
          <ul>
            <li><code>xRV_proxy</code> se usa en lugar de RE24: no hay estado de juego completo.</li>
            <li><code>altitude_category</code> es una clasificación gruesa, no altitud continua.</li>
            <li>Stuff+ físico usa solo shape (velo, spin, IVB, HB); no captura engaño ni repetición.</li>
          </ul>
        </app-tile>

        <app-tile label="Holdouts corridos" class="span-6">
          <ul>
            <li>Año: temporada 2026 completa como holdout temporal.</li>
            <li>Pitcher: pitchers completos fuera del ajuste.</li>
            <li>Juego: partición por juego para evitar fuga intra-juego.</li>
            <li>Categoría: evaluación cruzada entre categorías de altitud.</li>
          </ul>
          <p class="mt__blocked">
            <strong>Bloqueado:</strong> park holdout — sin <code>stadium_id</code> no se puede
            separar parque de categoría.
          </p>
        </app-tile>

        <app-tile label="Ilustración física · 2 240 m" class="span-12" tag="no calibrado en LMB para ese estadio" tagTone="warn">
          <p>
            A ~2 240 m el aire es ~18–20% menos denso: la fuerza Magnus cae de forma similar y un
            slider típico pierde ~2–4 in de barrido horizontal y ~1–3 in de IVB. Estas magnitudes son
            <strong>una ilustración física general</strong>, <u>no calibrada en LMB para ese estadio</u>;
            los Δ reportados en el dashboard provienen exclusivamente de comparaciones entre categorías.
          </p>
        </app-tile>
      </div>
    </div>
  `,
  styles: `
    .mt { display: flex; flex-direction: column; gap: 14px; }
    .mt h1 { margin: 0; font-size: 1.2rem; }
    .mt p { font-size: 1rem; color: var(--ink); line-height: 1.5; margin: 0 0 8px; }
    .mt ul { margin: 0; padding-left: 18px; font-size: 0.95rem; line-height: 1.5; color: var(--ink); }
    .mt li { margin-bottom: 5px; }
    .mt code { background: var(--bg); padding: 1px 5px; border-radius: 4px; font-size: 0.9rem; }
    .mt__glossary {
      margin: 0;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px 28px;
      dt { font-weight: 700; color: var(--ink); }
      dd { margin: 2px 0 0; font-size: 0.95rem; color: var(--muted); line-height: 1.45; }
    }
    .mt__flag {
      font-size: 0.88rem !important; font-weight: 700; color: var(--green);
      background: #ecfdf3; border-radius: 6px; padding: 6px 10px; display: inline-block;
    }
    .mt__blocked { color: var(--red) !important; }
  `,
})
export class MetodoPage {
  readonly ctx = inject(ScoutingContextService);
}
