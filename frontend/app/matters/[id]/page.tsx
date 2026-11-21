import type { Metadata } from "next";
import { MatterDetail } from "@/features/matters";

export const metadata: Metadata = { title: "Sprawa - Moje sprawy - Radar innowacji" };

export default async function MatterRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <main id="main" tabIndex={-1} className="page page-wide"><MatterDetail id={Number(id)} /></main>;
}
