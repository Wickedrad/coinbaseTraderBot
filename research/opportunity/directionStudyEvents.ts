import type { TimelyMoveDefinition } from './contractDataset';

/** Small sustained moves count. These settings are fixed before looking at their outcomes. */
export function directionStudyEvents(): TimelyMoveDefinition[] {
  return (['up', 'down'] as const).flatMap((direction) => [0.25, 0.5, 1].map((thresholdAtr) => ({
    id: `direction-${direction}-${thresholdAtr}atr-sustain5-v1`, kind: 'move' as const, direction,
    thresholdAtr, sustainSec: 5, sustainFraction: 0.75, priorWindowSec: 0,
  })));
}
