import { Component } from '@angular/core';
@Component({
  selector: 'app-metric-guide',
  template: `<details class="metric-guide"><summary>¿Qué significan estos números? <span class="eyebrow">Guía rápida de lectura</span></summary>
    <div class="metric-guide__grid">
      <div><strong>100 es la referencia</strong><p>Stuff+ evalúa las características físicas. Location+ evalúa ubicación y contexto. Pitching+ combina físicas y ubicación. Por encima de 100 indica una evaluación más favorable que la referencia de calibración; son índices provisionales.</p></div>
      <div><strong>Lee la forma del lanzamiento</strong><p>IVB es el movimiento vertical inducido, separado de la caída por gravedad. HB es el movimiento horizontal. Se miden en pulgadas; su signo indica dirección, no calidad. Spin mide las vueltas por minuto (rpm).</p></div>
      <div><strong>Cada escala cuenta algo distinto</strong><p>Pitch Value+ incluye ubicación, conteo y arsenal: no es Stuff+ físico ni carreras esperadas. En xRV aproximado, menos carreras favorecen al pitcher. No restes valores entre escalas. Swing en blanco significa que el bateador intenta y falla; en strike cantado no intenta.</p></div>
    </div></details>`
})
export class MetricGuideComponent {}
