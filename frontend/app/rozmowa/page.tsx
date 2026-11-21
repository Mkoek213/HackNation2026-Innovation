import type { Metadata } from "next";
import { Workspace } from "@/features/workspace";

export const metadata: Metadata = { title: "Rozmowa - Radar innowacji" };

export default function ConversationPage() {
  return <Workspace />;
}
