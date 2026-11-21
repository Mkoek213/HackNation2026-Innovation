import type { Metadata } from "next";
import { ContactPage } from "@/features/contact";

export const metadata: Metadata = { title: "Kontakt - Radar innowacji" };

export default function Contact() {
  return <main id="main" tabIndex={-1} className="page"><ContactPage /></main>;
}
