import { Injectable, computed, signal } from '@angular/core';
import { AltitudeCategory, PitchType, RouteMode } from '../models/domain.types';

/**
 * Estado compartido del scouting: pitcher, tipo de pitch, temporada,
 * categoría de altitud y modo de ruta (A = categorías, B = metadatos de estadio).
 * En la demo Ruta B está bloqueada porque no hay stadium_id reales.
 */
@Injectable({ providedIn: 'root' })
export class ScoutingContextService {
  readonly pitcherId = signal('p-0001');
  readonly pitchType = signal<PitchType | 'ALL'>('ALL');
  readonly season = signal<number | 'ALL'>('ALL');
  readonly category = signal<AltitudeCategory | 'ALL'>('ALL');
  readonly routeMode = signal<RouteMode>('A');
  /** En la demo los metadatos de estadio son simulados: Ruta B se marca como tal. */
  readonly stadiumMetadataSimulated = signal(true);

  readonly regimeLabel = computed(() =>
    this.routeMode() === 'A' ? 'Ruta A · categorías de altitud' : 'Ruta B · metadatos simulados',
  );

  selectPitcher(id: string): void {
    this.pitcherId.set(id);
  }

  selectPitchType(type: PitchType | 'ALL'): void {
    this.pitchType.set(type);
  }
}
