"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { session, type User } from "@/features/workspace";
import { AnalyticsView } from "./analytics";
import { DocumentsView } from "./documents";

// Non-admins get a login or forbidden message; admin APIs are never requested for them.
function AdminOnly({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    let active = true;
    session().then(account => { if (active) setUser(account); }, () => { if (active) setUser(null); });
    return () => { active = false; };
  }, []);

  if (user === undefined) return <p role="status" className="page-status">Wczytuję…</p>;
  if (!user) return <section className="page-intro"><h1>Wybierz rolę</h1><p>Ta część platformy jest dostępna po zalogowaniu jako administrator.</p><Button nativeButton={false} render={<Link href="/rozmowa" />}>Wybierz rolę</Button></section>;
  return user.role === "admin" ? children : <p role="alert" className="page-status">Ta część platformy jest dostępna tylko dla administratorów.</p>;
}

export function AnalyticsPage() { return <AdminOnly><AnalyticsView /></AdminOnly>; }
export function DocumentsPage() { return <AdminOnly><DocumentsView /></AdminOnly>; }
