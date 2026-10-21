import { MetricGuideComponent } from '../../shared/ui/metric-guide.component';
import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DataService } from '../../core/data-access/data.service';
import { ScoutingContextService } from '../../core/state/scouting-context.service';
import { ApiService } from '../../core/api/api.service';
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
 * - input fuera de distribución del pitcher → aviso; fuera de rangos físicos → bloqueo.
 * Con backend disponible los scores vienen de /predict (F8) y el contrafactual
 * de /simulate (F10 experimental); sin backend no se fabrican scores.
 */
@Component({
  selector: 'app-simulador-page',
  imports: [MetricGuideComponent, FormsModule, TileComponent, GaugeComponent, TrajectoryComponent,
    MovementChartComponent, StateBannerComponent, RecommendationsComponent],
  templateUrl: './simulador.page.html',
  styleUrl: './simulador.page.scss',
})
export class SimuladorPage {
  readonly mobileView = signal<'edit' | 'results'>('edit');
  protected readonly data = inject(DataService);
  protected readonly ctx = inject(ScoutingContextService);
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
  /** Contexto del evento F8: mano del bateador y conteo. */
  readonly batterSide = signal<'Right' | 'Left'>('Right');
  readonly balls = signal(0);
  readonly strikes = signal(0);

  readonly examples = this.data.examples;

  /** Scores reales del backend; null si el API no está disponible. */
  readonly live = signal<LiveScores | null>(null);
  /** Error de la última petición en modo API (p. ej. rechazo de validación). */
  readonly apiError = signal<string | null>(null);
  readonly apiPending = signal(false);
  private requestSeq = 0;
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private healthProbeAt = 0;

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.requestSeq++;
      if (this.debounce) clearTimeout(this.debounce);
    });
    // Recalcula al cambiar pitcher, bundles (carga/recarga) o cualquier control.
    // También dispara la primera evaluación al abrir la página.
    effect(() => {
      this.ctx.pitcherId();
      this.data.bundles();
      this.input();
      this.batterSide();
      this.balls();
      this.strikes();
      this.sourceCat();
      this.targetCat();
      this.refresh();
    });
  }

  /** Distribución observada del pitcher para el tipo seleccionado. */
  readonly reference = computed(() => {
    const b = this.data.bundleOf(this.ctx.pitcherId());
    if (!b) return null;
    const rows = b.arsenal.filter((r) => r.pitchType === this.input().pitchType);
    if (rows.length === 0) return null;
    const total = rows.reduce((sum, r) => sum + r.n, 0);
    const avg = (f: (r: (typeof rows)[number]) => number) =>
      rows.reduce((a, r) => a + f(r) * r.n, 0) / Math.max(total, 1);
    const avgOpt = (f: (r: (typeof rows)[number]) => number | undefined) => {
      const valid = rows.filter((r) => f(r) !== undefined);
      const n = valid.reduce((sum, r) => sum + r.n, 0);
      return n ? valid.reduce((sum, r) => sum + (f(r) ?? 0) * r.n, 0) / n : undefined;
    };
    // El eje medio debe ser un vector unitario: promediar sin/cos por separado
    // encoge el vector y el backend lo rechaza (sin²+cos²≈1). Se normaliza.
    const sin = avgOpt((r) => r.spinAxisSinAvg);
    const cos = avgOpt((r) => r.spinAxisCosAvg);
    const norm = sin !== undefined && cos !== undefined ? Math.hypot(sin, cos) : 0;
    return {
      velo: avg((r) => r.veloMphAvg),
      spin: avg((r) => r.spinRpmAvg),
      ivb: avg((r) => r.ivbInAvg),
      hb: avg((r) => r.hbInAvg),
      axisSin: norm && sin !== undefined ? sin / norm : undefined,
      axisCos: norm && cos !== undefined ? cos / norm : undefined,
      relHeight: avgOpt((r) => r.relHeightAvg),
      relSide: avgOpt((r) => r.relSideAvg),
      extension: avgOpt((r) => r.extensionAvg),
    };
  });

  /** ¿El shape está fuera de la distribución observada del pitcher? */
  readonly outOfDistribution = computed(() => {
    const ref = this.reference();
    if (!ref) return false;
    const i = this.input();
    return (
      Math.abs(i.veloMph - ref.velo) > 3 ||
      Math.abs(i.spinRpm - ref.spin) > 350 ||
      Math.abs(i.ivbIn - ref.ivb) > 6 ||
      Math.abs(i.hbIn - ref.hb) > 8
    );
  });

  /** Rangos físicos duros: fuera de esto el pitch no es físicamente plausible. */
  readonly physicallyInvalid = computed(() => {
    const i = this.input();
    return Object.entries(i).some(([key, v]) => key !== 'pitchType' && (typeof v !== 'number' || !Number.isFinite(v))) ||
      i.veloMph < 30 || i.veloMph > 110 || i.spinRpm < 0 || i.spinRpm > 5000 ||
      Math.abs(i.ivbIn) > 40 || Math.abs(i.hbIn) > 40 ||
      i.releaseHeightFt < 0 || i.releaseHeightFt > 10 || Math.abs(i.releaseSideFt) > 8 ||
      i.extensionFt < 0 || i.extensionFt > 10 || i.axisDeg < 0 || i.axisDeg > 360;
  });

  readonly stuffPlus = computed(() => this.live()?.stuffPlus ?? null);
  readonly locationPlus = computed(() => this.live()?.locationPlus ?? null);
  readonly pitchingPlus = computed(() => this.live()?.pitchingPlus ?? null);
  readonly targetMovement = computed(() => {
    const live = this.live();
    return live?.simStatus === 'experimental' && live.simTargetHb !== null && live.simTargetIvb !== null
      ? { hbIn: live.simTargetHb, ivbIn: live.simTargetIvb } : null;
  });

  readonly trajectory = computed(() => ({
    veloMph: this.input().veloMph,
    ivbIn: this.input().ivbIn,
    hbIn: this.input().hbIn,
    plateXIn: this.input().plateXIn,
    plateZIn: this.input().plateZIn,
  }));

  /**
   * Mapa de movimiento: pitches reales del pitcher coloreados por Stuff+
   * (rojo = más efectivo) + el pitch simulado como último punto marcado.
   */
  readonly mapPitches = computed<readonly PitchScore[]>(() => {
    const b = this.data.bundleOf(this.ctx.pitcherId());
    const i = this.input();
    const sim: PitchScore = {
      id: '__sim__', pitcherId: b?.pitcher.id ?? '', pitchType: i.pitchType,
      season: 0, category: this.sourceCat(), veloMph: i.veloMph, spinRpm: i.spinRpm,
      ivbIn: i.ivbIn, hbIn: i.hbIn, plateXIn: i.plateXIn, plateZIn: i.plateZIn,
      stuffPlus: this.stuffPlus(), locationPlus: this.locationPlus(),
      pitchingPlus: this.pitchingPlus(),
    };
    return [...(b?.pitches ?? []), sim];
  });
  readonly mapHighlight = computed(() => this.mapPitches().length - 1);
  readonly mapThrows = computed(
    () => this.data.bundleOf(this.ctx.pitcherId())?.pitcher.throws ?? 'R',
  );

  /**
   * Pitch record para el backend: físicas del input + contexto.
   * Eje, release y extensión proceden de los controles editables del formulario.
   * `pitcher_anon_id` activa la historia 2024 del pitcher en F10.
   */
  private toRecord(i: SimInput): Record<string, unknown> {
    const bundle = this.data.bundleOf(this.ctx.pitcherId());
    const throws = bundle?.pitcher.throws ?? 'R';
    const axis = i.axisDeg * Math.PI / 180;
    return {
      pitcher_anon_id: bundle?.pitcher.id,
      auto_pitch_type: PITCH_TYPE_TO_API[i.pitchType],
      pitcher_throws: throws === 'L' ? 'Left' : 'Right',
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
    this.live.set(null);
    this.apiError.set(null);
    this.apiPending.set(false);
    if (this.data.source() !== 'api' || this.physicallyInvalid()) {
      this.probeForRecovery();
      return;
    }
    const record = this.toRecord(this.input());
    const target = ALTITUDE_TO_API[this.targetCat()];
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
        if (!fam && !simRow) return;
        this.live.set({
          xrv: fam?.pitching?.xrv,
          stuffPlus: fam?.stuff?.score ?? null,
          locationPlus: fam?.location?.score ?? null,
          pitchingPlus: fam?.pitching?.score ?? null,
          warnings: predictionWarnings(fam?.pitching?.warnings ?? ''),
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

  loadReference(): void {
    const ref = this.reference();
    if (!ref) return;
    this.input.update((input) => ({
      ...input, veloMph: ref.velo, spinRpm: ref.spin, ivbIn: ref.ivb, hbIn: ref.hb,
      extensionFt: ref.extension ?? input.extensionFt,
      releaseHeightFt: ref.relHeight ?? input.releaseHeightFt,
      releaseSideFt: ref.relSide ?? input.releaseSideFt,
      axisDeg: ref.axisSin !== undefined && ref.axisCos !== undefined
        ? (Math.atan2(ref.axisSin, ref.axisCos) * 180 / Math.PI + 360) % 360 : input.axisDeg,
    }));
  }
}
