import type { Metadata } from "next";
import { InnovationsPage } from "@/features/knowledge";

export const metadata: Metadata = { title: "Baza innowacji - Radar innowacji" };

export default async function InnovationsRoute({ searchParams }: PageProps<"/knowledge/innovations">) {
  return <main id="main" tabIndex={-1} className="page page-knowledge"><InnovationsPage preset={await searchParams} /></main>;
}
