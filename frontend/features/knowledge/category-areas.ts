// Colour coding of innovation cards: six sectors fold into three areas so neighbouring cards stay
// distinguishable (the validated three-colour set: worst CVD ΔE 9.2, normal vision 24.0). The
// sector itself is always shown as text, so colour never carries identity alone. Colours live in
// app/globals.css (--area-*).

export type AreaId = "industry" | "digital" | "life";

export const AREAS: { id: AreaId; label: string }[] = [
  { id: "industry", label: "Przemysł, transport i kosmos" },
  { id: "digital", label: "ICT i cyfryzacja" },
  { id: "life", label: "Jakość życia i inne obszary" },
];

const AREA_OF_SECTOR: Record<string, AreaId> = {
  motoryzacja: "industry",
  lotnictwo: "industry",
  kosmos: "industry",
  ict: "digital",
  "jakosc-zycia": "life",
  inne: "life",
};

/** Area of a sector slug; undefined for unknown slugs (rendered with the neutral edge). */
export function areaOf(sector: string): AreaId | undefined {
  return AREA_OF_SECTOR[sector];
}
