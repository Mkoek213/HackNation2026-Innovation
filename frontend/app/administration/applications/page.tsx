import type { Metadata } from "next";
import { ApplicationsPage } from "@/features/administration";

export const metadata: Metadata = { title: "Pilotaże - Radar innowacji" };

export default function Page() {
  return <main id="main" tabIndex={-1} className="page page-wide"><ApplicationsPage /></main>;
}
