import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";
import { VisitTracker } from "@/components/visit-tracker";

export const metadata: Metadata = {
  title: "Radar innowacji - Podkarpackie Centrum Innowacji",
  description: "Odnajduj ukryte innowacje ze szkół, uczelni i samorządów, oceniaj ich potencjał i łącz je z partnerami, którzy mogą je wdrożyć.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="pl" suppressHydrationWarning><body><div className="app"><SiteHeader />{children}</div><VisitTracker /></body></html>;
}
