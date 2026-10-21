import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DataService } from '../../core/data-access/data.service';
import { ApiService, ApiSimRecord } from '../../core/api/api.service';
import { PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import {
  ALTITUDE_CATEGORIES,
  ALTITUDE_LABELS,
  AltitudeCategory,
  bandFor,
  PITCH_TYPES,
  PITCH_TYPE_NAMES,
  PitchScore,
  PitchType,
  SimulatorExample,
} from '../../core/models/domain.types';
import { TileComponent } from '../../shared/ui/tile.component';
import { GaugeComponent } from '../../shared/ui/gauge.component';
import { TrajectoryComponent } from '../../shared/ui/trajectory.component';
import { MovementChartComponent } from '../../shared/ui/movement-chart.component';
import { StateBannerComponent } from '../../shared/ui/state-banner.component';
import { predictionWarnings, productText } from '../../core/models/pitch-analysis';
import { RecommendationsComponent } from './recommendations.component';
import { ALTITUDE_TO_API } from './simulator-candidates';
import { movementReference } from './simulator-reference';

interface SimInput {
  pitchType: PitchType;
  veloMph: number;
  spinRpm: number;
  ivbIn: number;
  hbIn: number;
  plateXIn: number;
  plateZIn: number;
  extensionFt: number;
  releaseHeightFt: number;
  releaseSideFt: number;
  axisDeg: number;
}

interface LiveScores {
  input: SimInput;
  source: AltitudeCategory;
  target: AltitudeCategory;
  hand: 'Right' | 'Left';
  balls: number;
  strikes: number;
  stuffComparison?: ApiSimRecord['stuff_comparison'];
  xrv?: import('../../core/api/api.service').ApiPredictionFamily['xrv'];
  stuffPlus: number | null;
  locationPlus: number | null;
  pitchingPlus: number | null;
  warnings: string;
  simStatus: string | null;
  simDelta: number | null;
  simSourceScore: number | null;
  simTargetScore: number | null;
  simTargetIvb: number | null;
  simTargetHb: number | null;
  simScope: string | null;
  simReason: string | null;
}

/**
 * Simulador con contrato explícito:
 * - mover spin NO modifica IVB automáticamente (shape hipotético declarado),
 * - ubicación afecta Location+/Pitching+, no Stuff+ físico,
 * - fuera de rangos físicos → bloqueo. Laboratorio sin lanzador: el coach
 *   ingresa las físicas del pitch directamente; no hay referencia de arsenal.
 * Con backend disponible los scores vienen de /predict (F8) y el contrafactual
 * de /simulate (F10 experimental); sin backend no se fabrican scores.
 */
@Component({
  selector: 'app-simulador-page',
  imports: [FormsModule, TileComponent, GaugeComponent, TrajectoryComponent,
    MovementChartComponent, StateBannerComponent, RecommendationsComponent],
  templateUrl: './simulador.page.html',
  styleUrl: './simulador.page.scss',
})
export class SimuladorPage {
  readonly mobileView = signal<'edit' | 'results'>('edit');
  protected readonly data = inject(DataService);
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly pitchTypes = PITCH_TYPES;
  protected readonly pitchTypeNames = PITCH_TYPE_NAMES;
  protected readonly categories = ALTITUDE_CATEGORIES;
  protected readonly labels = ALTITUDE_LABELS;
  protected readonly bandFor = bandFor;

  readonly input = signal<SimInput>({
    pitchType: 'FB', veloMph: 93, spinRpm: 2350, ivbIn: 15, hbIn: -6,
    plateXIn: 0, plateZIn: 28,
    extensionFt: 6.2, releaseHeightFt: 6, releaseSideFt: 1.8, axisDeg: 150,
  });

  /** Categoría origen del pitch y destino del contrafactual F10. */
  readonly sourceCat = signal<AltitudeCategory>('No Altitude');
  readonly targetCat = signal<AltitudeCategory>('Extreme');
  /** Contexto del evento F8: mano del lanzador, mano del bateador y conteo. */
  readonly pitcherHand = signal<'Right' | 'Left'>('Right');
  readonly batterSide = signal<'Right' | 'Left'>('Right');
  readonly balls = signal(0);
  readonly strikes = signal(0);

  readonly examples = this.data.examples;

  /** Scores reales del backend; null si el API no está disponible. */
  readonly live = signal<LiveScores | null>(null);
  /** Error de la última petición en modo API (p. ej. rechazo de validación). */
  readonly apiError = signal<string | null>(null);
  readonly apiPending = signal(false);
  readonly stale = computed(() => this.live() !== null && (this.apiPending() || this.apiError() !== null));
  readonly shownInput = computed(() => this.live()?.input ?? this.input());
  private requestSeq = 0;
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private healthProbeAt = 0;

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.requestSeq++;
      if (this.debounce) clearTimeout(this.debounce);
    });
    // Recalcula al mover cualquier control. También dispara la primera
    // evaluación al abrir la página.
    effect(() => {
      this.input();
      this.pitcherHand();
      this.batterSide();
      this.balls();
      this.strikes();
      this.sourceCat();
      this.targetCat();
      this.refresh();
    });
  }

  /** Rangos físicos duros: fuera de esto el pitch no es físicamente plausible. */
  readonly physicallyInvalid = computed(() => {
    const i = this.input();
    return Object.entries(i).some(([key, v]) => key !== 'pitchType' && (typeof v !== 'number' || !Number.isFinite(v))) ||
      i.veloMph < 30 || i.veloMph > 110 || i.spinRpm < 0 || i.spinRpm > 5000 ||
      Math.abs(i.ivbIn) > 40 || Math.abs(i.hbIn) > 40 ||
      i.releaseHeightFt < 0 || i.releaseHeightFt > 10 || Math.abs(i.releaseSideFt) > 8 ||
      i.extensionFt < 0 || i.extensionFt > 10 || i.axisDeg < 0 || i.axisDeg > 360;
  });

  readonly stuffPlus = computed(() => this.live()?.stuffComparison?.source_score ?? this.live()?.stuffPlus ?? null);
  readonly locationPlus = computed(() => this.live()?.locationPlus ?? null);
  readonly pitchingPlus = computed(() => this.live()?.pitchingPlus ?? null);
  readonly comparison = computed(() => this.live()?.stuffComparison);
  readonly targetStuff = computed(() => this.comparison()?.status === 'experimental'
    ? this.comparison()?.target_score ?? null : null);
  readonly stuffDelta = computed(() => this.comparison()?.status === 'experimental'
    ? this.comparison()?.delta_score ?? null : null);
  readonly targetMovement = computed(() => {
    const live = this.live();
    return live?.simStatus === 'experimental' && live.simTargetHb !== null && live.simTargetIvb !== null
      ? { hbIn: live.simTargetHb, ivbIn: live.simTargetIvb } : null;
  });

  readonly trajectory = computed(() => ({
    veloMph: this.shownInput().veloMph,
    ivbIn: this.shownInput().ivbIn,
    hbIn: this.shownInput().hbIn,
    plateXIn: this.shownInput().plateXIn,
    plateZIn: this.shownInput().plateZIn,
  }));

  readonly reference = computed(() => {
    const type = this.shownInput().pitchType;
    const hand = this.mapThrows();
    const pitches = this.data.source() === 'api'
      ? this.data.bundles().filter((b) => b.pitcher.throws === hand)
        .flatMap((b) => b.pitches).filter((p) => p.pitchType === type && p.partition !== 'test_2026') : [];
    return movementReference(pitches);
  });

  readonly mapPitches = computed<readonly PitchScore[]>(() => {
    const i = this.shownInput();
    const sim: PitchScore = {
      id: '__sim__', pitcherId: '', pitchType: i.pitchType,
      season: 0, category: this.live()?.source ?? this.sourceCat(), veloMph: i.veloMph, spinRpm: i.spinRpm,
      ivbIn: i.ivbIn, hbIn: i.hbIn, plateXIn: i.plateXIn, plateZIn: i.plateZIn,
      stuffPlus: this.stuffPlus(), locationPlus: this.locationPlus(),
      pitchingPlus: this.pitchingPlus(),
    };
    return [...this.reference().sample, sim];
  });
  readonly mapHighlight = computed(() => this.reference().sample.length);
  readonly mapThrows = computed(() => (this.live()?.hand ?? this.pitcherHand()) === 'Left' ? 'L' : 'R');

  /**
   * Pitch record para el backend: físicas del input + contexto.
   * Eje, release y extensión proceden de los controles editables del formulario.
   * Sin lanzador: F10 usa la referencia de grupo, no una historia individual.
   */
  private toRecord(i: SimInput): Record<string, unknown> {
    const axis = i.axisDeg * Math.PI / 180;
    return {
      auto_pitch_type: PITCH_TYPE_TO_API[i.pitchType],
      pitcher_throws: this.pitcherHand(),
      rel_speed: i.veloMph,
      spin_rate: i.spinRpm,
      spin_axis_sin: Math.sin(axis),
      spin_axis_cos: Math.cos(axis),
      rel_height: i.releaseHeightFt,
      rel_side: i.releaseSideFt,
      extension: i.extensionFt,
      induced_vert_break: i.ivbIn,
      horz_break: i.hbIn,
      plate_loc_height: i.plateZIn / 12,
      plate_loc_side: i.plateXIn / 12,
      balls: this.balls(),
      strikes: this.strikes(),
      batter_side: this.batterSide(),
      altitude_category: ALTITUDE_TO_API[this.sourceCat()],
    };
  }

  private refresh(): void {
    if (this.debounce) clearTimeout(this.debounce);
    const seq = ++this.requestSeq;
    this.apiError.set(null);
    this.apiPending.set(false);
    if (this.data.source() !== 'api' || this.physicallyInvalid()) {
      this.live.set(null);
      this.probeForRecovery();
      return;
    }
    const input = { ...this.input() };
    const source = this.sourceCat(), targetCategory = this.targetCat(), hand = this.pitcherHand();
    const balls = this.balls(), strikes = this.strikes();
    const record = this.toRecord(input);
    const target = ALTITUDE_TO_API[targetCategory];
    this.apiPending.set(true);
    this.debounce = setTimeout(() => {
      void Promise.allSettled([
        this.api.predict([record]),
        this.api.simulate([record], target),
      ]).then(([pred, sim]) => {
        if (seq !== this.requestSeq) return; // respuesta obsoleta
        this.apiPending.set(false);
        if (pred.status === 'rejected' || sim.status === 'rejected') {
          this.apiError.set('No se pudo completar ' + (pred.status === 'rejected' ? 'la evaluación del lanzamiento' : 'la comparación de altitud') + '. Reintenta el cálculo.');
        }
        const fam = pred.status === 'fulfilled' ? pred.value.records[0] : undefined;
        const simRow = sim.status === 'fulfilled' ? sim.value.records[0] : null;
        if (!fam && !simRow) {
          this.apiError.set('No se recibieron estimaciones para este escenario. Reintenta el cálculo.');
          return;
        }
        this.live.set({
          input, source, target: targetCategory, hand, balls, strikes,
          stuffComparison: simRow?.stuff_comparison,
          xrv: fam?.pitching?.xrv,
          stuffPlus: fam?.stuff?.score ?? null,
          locationPlus: fam?.location?.score ?? null,
          pitchingPlus: fam?.pitching?.score ?? null,
          warnings: predictionWarnings([fam?.stuff?.warnings, simRow?.stuff_comparison?.warnings].filter(Boolean).join(';')),
          simStatus: simRow?.status ?? null,
          simDelta: simRow?.delta_score ?? null,
          simSourceScore: simRow?.source_score ?? null,
          simTargetScore: simRow?.target_score ?? null,
          simTargetIvb: simRow?.target_ivb ?? null,
          simTargetHb: simRow?.target_hb ?? null,
          simScope: simRow?.scope ?? null,
          simReason: simRow?.reason ? productText(simRow.reason) : null,
        });
      });
    }, 600);
  }

  /**
   * Si la app quedó en modo sintético pero el backend volvió, sondea /health
   * (máx. 1 vez cada 5 s) y recarga datos para salir del fallback sola.
   */
  private probeForRecovery(): void {
    const now = Date.now();
    if (now - this.healthProbeAt < 5000) return;
    this.healthProbeAt = now;
    void this.api.health().then((ok) => {
      if (ok && this.data.source() !== 'api') void this.data.reload();
    });
  }

  retry(): void { this.refresh(); }

  set<K extends keyof SimInput>(key: K, value: SimInput[K]): void {
    this.input.update((i) => ({ ...i, [key]: value }));
  }

  setSourceCat(value: string): void {
    this.sourceCat.set(value as AltitudeCategory);
  }

  setTargetCat(value: string): void {
    this.targetCat.set(value as AltitudeCategory);
  }

  setBatterSide(value: string): void {
    this.batterSide.set(value as 'Right' | 'Left');
  }

  setBalls(value: number): void {
    this.balls.set(value);
  }

  setStrikes(value: number): void {
    this.strikes.set(value);
  }

  loadExample(ex: SimulatorExample): void {
    this.input.update((input) => ({ ...input, ...ex }));
  }

  setPitcherHand(value: string): void {
    this.pitcherHand.set(value as 'Right' | 'Left');
  }
}
