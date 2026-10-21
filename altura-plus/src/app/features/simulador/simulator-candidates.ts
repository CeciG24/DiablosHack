import { AltitudeCategory } from '../../core/models/domain.types';

export const ALTITUDE_TO_API: Record<AltitudeCategory, string> = {
  Extreme: 'Extreme Altitude', Medium: 'Medium Altitude', 'No Altitude': 'No Altitude',
};
