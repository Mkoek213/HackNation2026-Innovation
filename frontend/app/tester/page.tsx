import type { Metadata } from "next";
import { VolunteerPage } from "@/features/tester";

export const metadata: Metadata = { title: "Zgłoś gotowość do pilotażu - Radar innowacji" };

export default function TesterPage() {
  return <main id="main" tabIndex={-1} className="page"><VolunteerPage /></main>;
}
