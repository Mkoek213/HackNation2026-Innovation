"use client";

import Link from "next/link";
import type { ComponentType } from "react";
import { Button } from "@/components/ui/button";
import { ArrowRight, FlaskConical, Handshake, Lightbulb, MessagesSquare, Search } from "@/components/ui/icons";
import { getCatalog, useLoad } from "@/features/knowledge";

type IconType = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

const entries: { href: string; icon: IconType; title: string; text: string; action: string }[] = [
  { href: "/rozmowa?nowa=1", icon: MessagesSquare, title: "Znajdź rozwiązanie", text: "Opisz potrzebę szkoły, uczelni, firmy lub urzędu. Asystent pomoże wyszukać i porównać rozwiązania.", action: "Opisz potrzebę" },
  { href: "/knowledge/innovations", icon: Lightbulb, title: "Baza innowacji", text: "Sprawdź etap wdrożenia, dowody i możliwości zastosowania polskich rozwiązań.", action: "Przeglądaj innowacje" },
  { href: "/tester", icon: FlaskConical, title: "Zostań partnerem pilotażu", text: "Jeśli Twoja instytucja może przetestować rozwiązanie w praktyce, dołącz do bazy partnerów.", action: "Zgłoś się" },
];

const steps: { icon: IconType; title: string; text: string }[] = [
  { icon: MessagesSquare, title: "Opisz potrzebę", text: "Napisz lub podyktuj, jaki problem chcesz rozwiązać i w jakiej instytucji." },
  { icon: Search, title: "Sprawdź dowody", text: "Porównaj etap wdrożenia, wiarygodność źródeł i możliwość zastosowania w innym miejscu." },
  { icon: Handshake, title: "Zaplanuj wdrożenie", text: "Sprawdź warunki wdrożenia lub zgłoś gotowość do pilotażu wybranego rozwiązania." },
];

const examples = [
  "Jak szkoła może wdrożyć cyfrowe metody nauczania?",
  "Jak gmina może udostępnić płatności online?",
  "Jak zautomatyzować transport wewnątrz magazynu?",
];

/** Polish plural form: 1 innowacja, 2–4 innowacje, 5+ innowacji (12–14 take the last form). */
function plural(count: number, one: string, few: string, many: string) {
  if (count === 1) return one;
  const tens = count % 100, units = count % 10;
  return units >= 2 && units <= 4 && (tens < 12 || tens > 14) ? few : many;
}

export function HomePage() {
  const innovations = useLoad(() => getCatalog("limit=1"), "confirmed-innovations");
  return <main id="main" tabIndex={-1} className="home">
    <section className="home-hero" aria-labelledby="home-title">
      <div className="home-hero-text">
        <p className="home-eyebrow">Radar innowacji · Podkarpackie Centrum Innowacji</p>
        <h1 id="home-title">Znajdź polskie innowacje gotowe do zastosowania</h1>
        <p className="home-lead">Radar odkrywa rozwiązania z publicznych źródeł. Porównaj dowody, sprawdź, gdzie już działają, i zaplanuj następny krok w swojej instytucji.</p>
        <div className="home-actions">
          <Button size="lg" nativeButton={false} render={<Link href="/knowledge/innovations" />}>Znajdź rozwiązanie<ArrowRight aria-hidden="true" /></Button>
          <Button size="lg" variant="outline" nativeButton={false} render={<Link href="/rozmowa?nowa=1" />}>Zapytaj asystenta</Button>
        </div>
        {innovations && <dl className="home-figures">
          {innovations && <div><dt>{plural(innovations.total, "innowacja", "innowacje", "innowacji")} w bazie</dt><dd>{innovations.total}</dd></div>}
        </dl>}
      </div>
      <aside className="home-examples" aria-labelledby="examples-title">
        <h2 id="examples-title">O co możesz zapytać</h2>
        <ul>{examples.map(text => <li key={text}><Link href={`/rozmowa?pytanie=${encodeURIComponent(text)}`}><MessagesSquare aria-hidden={true} size={18} /><span>{text}</span></Link></li>)}</ul>
        <Link className="home-examples-link" href="/rozmowa?nowa=1">Zadaj własne pytanie<ArrowRight aria-hidden="true" size={16} /></Link>
      </aside>
    </section>

    <section className="home-section" aria-labelledby="entries-title">
      <h2 id="entries-title">Od czego zacząć</h2>
      <ul className="home-entries">{entries.map(({ href, icon: Icon, title, text, action }) => <li key={href}>
        <Link className="home-entry" href={href}>
          <span className="entry-icon"><Icon aria-hidden={true} size={22} /></span>
          <span className="home-entry-title">{title}</span>
          <span className="home-entry-text">{text}</span>
          <span className="entry-more">{action}<ArrowRight aria-hidden="true" size={16} /></span>
        </Link>
      </li>)}</ul>
    </section>

    <section className="home-section" aria-labelledby="steps-title">
      <h2 id="steps-title">Jak to działa</h2>
      <ol className="home-steps">{steps.map(({ icon: Icon, title, text }, index) => <li key={title}>
        <span className="home-step-number" aria-hidden="true">{index + 1}</span>
        <div>
          <h3><Icon aria-hidden={true} size={18} />{title}</h3>
          <p>{text}</p>
        </div>
      </li>)}</ol>
    </section>

  </main>;
}
