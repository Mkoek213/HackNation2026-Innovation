"use client";

import { useEffect, useState, type ReactNode } from "react";
import { VolunteerPage } from "@/features/tester";
import { session, type User } from "@/features/workspace";
import { AnalyticsView } from "./analytics";
import { ApplicationsView } from "./applications";
import { DocumentsView } from "./documents";

// Non-admins get the pool view's own login or forbidden message; admin APIs are never requested for them.
function AdminOnly({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    let active = true;
    session().then(account => { if (active) setUser(account); }, () => { if (active) setUser(null); });
    return () => { active = false; };
  }, []);

  if (user === undefined) return <p role="status" className="page-status">Wczytuję…</p>;
  return user?.role === "admin" ? children : <VolunteerPage admin />;
}

export function TesterPoolPage() { return <VolunteerPage admin />; }
export function ApplicationsPage() { return <AdminOnly><ApplicationsView /></AdminOnly>; }
export function AnalyticsPage() { return <AdminOnly><AnalyticsView /></AdminOnly>; }
export function DocumentsPage() { return <AdminOnly><DocumentsView /></AdminOnly>; }
