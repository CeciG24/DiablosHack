import { PITCH_TYPE_TO_API } from '../../core/api/api-mappers';
import { AltitudeCategory, ArsenalRow, Pitcher } from '../../core/models/domain.types';

export const ALTITUDE_TO_API: Record<AltitudeCategory, string> = {
  Extreme: 'Extreme Altitude', Medium: 'Medium Altitude', 'No Altitude': 'No Altitude',
};

export function arsenalCandidates(rows: readonly ArsenalRow[], pitcher: Pitcher, source: AltitudeCategory) {
  return rows.filter((row) => row.season === 2025 && row.category === source).flatMap((row) => {
    const values = [row.veloMphAvg, row.spinRpmAvg, row.ivbInAvg, row.hbInAvg,
      row.spinAxisSinAvg, row.spinAxisCosAvg, row.relHeightAvg, row.relSideAvg, row.extensionAvg];
    if (values.some((v) => v == null || !Number.isFinite(v))) return [];
    const sin = row.spinAxisSinAvg ?? 0;
    const cos = row.spinAxisCosAvg ?? 0;
    const norm = Math.hypot(sin, cos);
    if (!norm) return [];
    return [{
      pitcher_anon_id: pitcher.id, auto_pitch_type: PITCH_TYPE_TO_API[row.pitchType],
      pitcher_throws: pitcher.throws === 'L' ? 'Left' : 'Right',
      rel_speed: row.veloMphAvg, spin_rate: row.spinRpmAvg,
      induced_vert_break: row.ivbInAvg, horz_break: row.hbInAvg,
      spin_axis_sin: sin / norm, spin_axis_cos: cos / norm,
      rel_height: row.relHeightAvg, rel_side: row.relSideAvg, extension: row.extensionAvg,
      altitude_category: ALTITUDE_TO_API[source],
    }];
  }).slice(0, 50);
}
