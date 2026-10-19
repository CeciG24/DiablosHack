import { Component, computed, effect, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { DataService } from '../../core/data-access/data.service';
import { PITCH_TYPE_NAMES, PitchType } from '../../core/models/domain.types';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ApiService, ApiProfile, ApiScoutingRow } from '../../core/api/api.service';
import { StateBannerComponent } from '../../shared/ui/state-banner.component';

interface Recommendation {
  title: string;
  evidence: string;
  assumptions: string;
  strength: 'alta' | 'media' | 'baja';
  n: number;
  nextAction: string;
}

/** Ficha de decisión: recomendaciones derivadas de los datos, con soporte explícito. */
@Component({
  selector: 'app-scouting-page',
  imports: [RouterLink, DecimalPipe, StateBannerComponent],
  templateUrl: './scouting.page.html',
  styleUrl: './scouting.page.scss',
})
export class ScoutingPage {
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
  private readonly api = inject(ApiService);

  readonly bundle = computed(() => this.data.bundleOf(this.ctx.pitcherId()));

  /** Ranking liga-wide pitcher×tipo de /api/v1/scouting (solo en modo API). */
  readonly leaderboard = signal<readonly ApiScoutingRow[]>([]);
  readonly leaderboardScope = signal<string | null>(null);
  /** Perfil ideal + respuestas a las 3 preguntas del brief (/api/v1/profile). */
  readonly profile = signal<ApiProfile | null>(null);

  constructor() {
    effect(() => {
      if (this.data.source() === 'api') {
        void this.api.scouting(50, 15).then((r) => {
          this.leaderboard.set(r.records);
          this.leaderboardScope.set(r.scope);
        }).catch(() => this.leaderboard.set([]));
        void this.api.profile().then((p) => this.profile.set(p))
          .catch(() => this.profile.set(null));
      } else {
        this.leaderboard.set([]);
        this.leaderboardScope.set(null);
        this.profile.set(null);
      }
    });
  }

  readonly recommendations = computed<readonly Recommendation[]>(() => {
    const b = this.bundle();
    if (!b) return [];
    const recs: Recommendation[] = [];

    const stuff = b.stuffPlus;
    const nStuff = stuff.n;
    const stuffStrength = nStuff >= 400 ? 'alta' : nStuff >= 120 ? 'media' : 'baja';
    if (stuff.value >= 105) {
      recs.push({
        title: 'Perfil favorable',
        evidence: `Stuff+ ${stuff.value} con IC ${stuff.ci[0]}–${stuff.ci[1]} sobre n=${nStuff} pitches.`,
        assumptions: 'Comparación entre categorías de altitud; un efecto observado en un bucket no implica causalidad de un parque específico.',
        strength: stuffStrength,
        n: nStuff,
        nextAction: 'Bullpen de confirmación en otra categoría de altitud antes de asignar un rol alto.',
      });
    }

    // Pareja No Altitude ↔ Extreme en cualquier dirección (el backend ordena
    // NoAlt→Extreme; el generador sintético Extreme→NoAlt). Se orienta a
    // "Extreme − No Altitude": negativo = el pitch empeora en altura extrema.
    const pair = b.deltas.find(
      (d) =>
        d.pitchType === 'FB' &&
        d.deltaStuffPlus !== null &&
        ((d.scenarioA === 'No Altitude' && d.scenarioB === 'Extreme') ||
          (d.scenarioA === 'Extreme' && d.scenarioB === 'No Altitude')),
    );
    const extremeDelta =
      pair && pair.scenarioA === 'No Altitude' ? pair.deltaStuffPlus! : -(pair?.deltaStuffPlus ?? 0);
    if (pair && pair.regime !== 'insuficiente' && extremeDelta < -3) {
      recs.push({
        title: 'Riesgo de contacto duro en altura extrema',
        evidence: `Δ Stuff+ FB en Extreme = ${extremeDelta} pts (IC ${pair.ci?.[0]} a ${pair.ci?.[1]}).`,
        assumptions: 'Supone shape estable del pitcher y ubicación comparable entre escenarios; Extreme ≠ un estadio nombrado.',
        strength: pair.regime === 'interpolado' ? 'alta' : 'media',
        n: pair.nA + pair.nB,
        nextAction: 'Sesión corta con Trackman en categoría Extreme para validar shape.',
      });
    }

    const byType = new Map<PitchType, { sum: number; n: number }>();
    for (const row of b.arsenal) {
      const acc = byType.get(row.pitchType) ?? { sum: 0, n: 0 };
      acc.sum += row.stuffPlus * row.n;
      acc.n += row.n;
      byType.set(row.pitchType, acc);
    }
    let worst: { type: PitchType; stuff: number; n: number } | null = null;
    for (const [type, acc] of byType) {
      const stuff = acc.sum / Math.max(acc.n, 1);
      if (!worst || stuff < worst.stuff) worst = { type, stuff, n: acc.n };
    }
    if (worst && worst.stuff < 98) {
      recs.push({
        title: `Candidato de desarrollo: ${PITCH_TYPE_NAMES[worst.type]}`,
        evidence: `Stuff+ ${Math.round(worst.stuff)} en el tipo más débil del arsenal (n=${worst.n}).`,
        assumptions: 'El rediseño supone margen de eje/eficiencia de spin sin degradar Location+.',
        strength: worst.n >= 120 ? 'media' : 'baja',
        n: worst.n,
        nextAction: 'Diseño de pitch en bullpen: ajustar eje de spin antes de probar en juego.',
      });
    }

    if (recs.length === 0) {
      recs.push({
        title: 'Sin señal clara',
        evidence: 'Ninguna recomendación supera el umbral de evidencia con los datos disponibles.',
        assumptions: 'La ausencia de señal no implica ausencia de efecto; puede faltar muestra.',
        strength: 'baja',
        n: nStuff,
        nextAction: 'Recolectar más pitches en la categoría objetivo antes de decidir.',
      });
    }
    return recs;
  });
}
