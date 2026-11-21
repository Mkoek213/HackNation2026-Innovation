import type { Metadata } from "next";
import { TesterPoolPage } from "@/features/administration";

export const metadata: Metadata = { title: "Baza partnerów - Radar innowacji" };

export default function Page() {
  return <main id="main" tabIndex={-1} className="page page-wide"><TesterPoolPage /></main>;
}
