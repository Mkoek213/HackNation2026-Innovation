// Colour coding of innovation cards by the three FAQ areas (the validated three-colour set: worst CVD
// ΔE 9.2, normal vision 24.0). The area is always shown as text, so colour never carries identity
// alone. Colours live in app/globals.css (--area-*).
import { innovationAreas } from "./api";

export type AreaId = keyof typeof innovationAreas;

export const AREAS = (Object.keys(innovationAreas) as AreaId[]).map(id => ({ id, label: innovationAreas[id] }));

/** Area of a card; undefined when unknown (rendered with the neutral edge). */
export function areaOf(area: string | null): AreaId | undefined {
  return area && area in innovationAreas ? area as AreaId : undefined;
}
