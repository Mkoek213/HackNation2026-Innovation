import type { Metadata } from "next";
import { HomePage } from "@/features/home";

export const metadata: Metadata = { title: "Radar innowacji" };

export default function Home() {
  return <HomePage />;
}
