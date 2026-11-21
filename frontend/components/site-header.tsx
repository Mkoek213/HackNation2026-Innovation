"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AccessibilityBar } from "@/components/accessibility-bar";
import { RadarMark, LogOut } from "@/components/ui/icons";
import { api, notifySession, session, sessionEvent, type User } from "@/features/workspace";

type Tab = { href: string; label: string; match?: (pathname: string) => boolean };
const tabs: Tab[] = [
  { href: "/rozmowa", label: "Rozmowa" },
  { href: "/matters", label: "Moje sprawy" },
  { href: "/knowledge/innovations", label: "Baza innowacji" },
];
// Reachable without signing in or starting a chat; always the last tab.
const contactTab: Tab = { href: "/contact", label: "Kontakt" };
const adminTabs: Tab[] = [
  { href: "/administration/analytics", label: "Analityka" },
  { href: "/administration/documents", label: "Dokumenty" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [wrapped, setWrapped] = useState(false);
  const headerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let active = true;
    const load = () => session().then(account => { if (active) setUser(account); }).catch(() => { if (active) setUser(null); });
    void load();
    window.addEventListener(sessionEvent, load);
    return () => { active = false; window.removeEventListener(sessionEvent, load); };
  }, []);

  // Tabs that do not fit beside the brand and account controls (many admin tabs, enlarged font) move to their own row
  // instead of being clipped. Mobile has its own wrapping layout. --header-h follows the real height for page layouts.
  useLayoutEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const mobile = window.matchMedia("(max-width: 760px)");
    const measure = () => {
      const [brand, nav, account] = [".site-brand", ".site-tabs", ".site-account"].map(selector => header.querySelector<HTMLElement>(selector));
      if (!brand || !nav || !account) return;
      const style = getComputedStyle(header);
      const gap = parseFloat(style.columnGap) || 0;
      const links = [...nav.children] as HTMLElement[];
      const tabs = links.reduce((sum, link) => sum + link.offsetWidth, 0) + Math.max(0, links.length - 1) * (parseFloat(getComputedStyle(nav).columnGap) || 0);
      const needed = brand.offsetWidth + tabs + account.offsetWidth + 2 * gap + parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      const next = !mobile.matches && needed > header.clientWidth;
      setWrapped(next);
      if (next) document.documentElement.style.setProperty("--header-h", `${header.offsetHeight}px`);
      else document.documentElement.style.removeProperty("--header-h");
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    for (const child of header.querySelectorAll(".site-brand, .site-tabs > a, .site-account")) observer.observe(child);
    mobile.addEventListener("change", measure);
    return () => { observer.disconnect(); mobile.removeEventListener("change", measure); document.documentElement.style.removeProperty("--header-h"); };
  }, [user]);

  async function logout() {
    try { await api("auth/logout", "POST"); } finally {
      notifySession();
      // A full reload, not router.push, drops every cached conversation of the signed-out account.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/");
    }
  }

  const links = [...tabs, ...(user?.role === "admin" ? adminTabs : []), contactTab];
  const current = (tab: Tab) => tab.match ? tab.match(pathname) : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
  return <header ref={headerRef} className="site-header" data-wrapped={wrapped || undefined}>
    <a className="skip-link" href="#main">Przejdź do treści</a>
    <Link className="site-brand" href="/" aria-label="Radar innowacji, strona główna">
      <span className="site-mark"><RadarMark aria-hidden="true" size={18} /></span>
      <span className="site-name">Radar innowacji<span className="site-name-long"> · PCI</span></span>
    </Link>
    {/* Public pages (home, knowledge) need the menu before sign-in; the other tabs ask for a role themselves. */}
    <nav aria-label="Główna nawigacja" className="site-tabs">
      {links.map(tab => <Link key={tab.href} href={tab.href} aria-current={current(tab) ? "page" : undefined}>{tab.label}</Link>)}
    </nav>
    <div className="site-account">
      <AccessibilityBar />
      {user && <>
        <span className="site-user">{user.username}</span>
        <button type="button" className="site-logout" onClick={() => void logout()} aria-label="Wyloguj się"><LogOut aria-hidden="true" size={18} /><span className="site-logout-label">Wyloguj</span></button>
      </>}
    </div>
  </header>;
}
