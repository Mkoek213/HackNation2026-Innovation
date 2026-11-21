import type { Metadata } from "next";
import { MatterList } from "@/features/matters";

export const metadata: Metadata = { title: "Moje sprawy - Radar innowacji" };

export default function MattersPage() {
  return <main id="main" tabIndex={-1} className="page page-wide"><MatterList /></main>;
}
