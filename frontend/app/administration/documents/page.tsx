import type { Metadata } from "next";
import { DocumentsPage } from "@/features/administration";

export const metadata: Metadata = { title: "Dokumenty bazy wiedzy - Radar innowacji" };

export default function Page() {
  return <main id="main" tabIndex={-1} className="page page-wide"><DocumentsPage /></main>;
}
