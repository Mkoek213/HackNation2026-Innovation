"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ComponentType } from "react";
import { Button } from "@/components/ui/button";
import { ArrowRight, Building, Handshake, Lightbulb, MessagesSquare, Search } from "@/components/ui/icons";
import { getCatalog, getTaxonomy, innovationAreas, useLoad } from "@/features/knowledge";

type IconType = ComponentType<{ size?: number; "aria-hidden"?: boolean }>;

const areas: { id: keyof typeof innovationAreas; icon: IconType; text: string }[] = [
  { id: "technologia", icon: Lightbulb, text: "Nowe technologie, produkty i rozwiązania techniczne z uczelni, instytutów i firm." },
  { id: "edukacja", icon: MessagesSquare, text: "Metody nauczania, narzędzia edukacyjne i programy rozwoju szkół oraz uczelni." },
  { id: "administracja", icon: Building, text: "Rozwiązania usprawniające pracę urzędów, samorządów i instytucji publicznych." },
];

const steps: { icon: IconType; title: string; text: string }[] = [
  { icon: Search, title: "Znajdź rozwiązanie", text: "Wyszukaj według potrzeby, obszaru, województwa i poziomu wdrożenia albo opisz potrzebę asystentowi." },
  { icon: Lightbulb, title: "Porównaj według kryteriów", text: "Sprawdź poziom wdrożenia, innowacyjność, potencjał zastosowania i wiarygodność wraz ze źródłem." },
  { icon: Handshake, title: "Zaplanuj wdrożenie", text: "Zobacz potencjalnych odbiorców, proponowaną ścieżkę, pierwszy krok i mierniki efektu." },
];

const examples = [
  "Jak gmina może udostępnić płatności online?",
  "Jakie rozwiązania pomagają szkołom uczyć programowania?",
  "Co sprawdziło się w elektronicznym obiegu dokumentów w urzędzie?",
];

/** Polish plural form: 1 innowacja, 2–4 innowacje, 5+ innowacji (12–14 take the last form). */
function plural(count: number, one: string, few: string, many: string) {
  if (count === 1) return one;
  const tens = count % 100, units = count % 10;
  return units >= 2 && units <= 4 && (tens < 12 || tens > 14) ? few : many;
}

const count = (params: string) => getCatalog(`limit=1&${params}`).then(page => page.total);
const catalog = (params: Record<string, string>) => `/knowledge/innovations?${new URLSearchParams(params)}`;

export function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const taxonomy = useLoad(getTaxonomy, "taxonomy");
  const totals = useLoad(() => Promise.all([
    count(""), count("confirmed_only=true"), count("region=Podkarpackie"),
    ...areas.map(area => count(`area=${area.id}`)),
  ]), "home-totals");
  const [all = 0, confirmed = 0, podkarpackie, ...byArea] = totals || [];
  return <main id="main" tabIndex={-1} className="home">
    <section className="home-hero" aria-labelledby="home-title">
      <div className="home-hero-text">
        <p className="home-eyebrow">Radar innowacji · Podkarpackie Centrum Innowacji</p>
        <h1 id="home-title">Znajdź polskie innowacje, które już działają</h1>
        <p className="home-lead">Radar zbiera rozwiązania z publicznych rejestrów i raportów wdrożeń z całej Polski, ocenia je według jawnych kryteriów i podpowiada, jak przenieść je do Twojej instytucji.</p>
        <form className="home-search" role="search" onSubmit={event => { event.preventDefault(); router.push(catalog(query.trim() ? { q: query.trim() } : {})); }}>
          <label className="search-field grow">
            <Search aria-hidden="true" size={18} />
            <span className="sr-only">Czego potrzebujesz?</span>
            <input type="search" maxLength={200} placeholder="Np. e-usługi w gminie, robotyka w szkole" value={query} onChange={e => setQuery(e.target.value)} />
          </label>
          <Button type="submit" size="lg">Szukaj<ArrowRight aria-hidden="true" /></Button>
        </form>
        <div className="home-actions">
          <Button size="lg" variant="outline" nativeButton={false} render={<Link href="/rozmowa?nowa=1" />}>Opisz potrzebę asystentowi</Button>
        </div>
        {totals && <dl className="home-figures">
          <div><dt>{plural(all, "innowacja", "innowacje", "innowacji")} w bazie</dt><dd>{all}</dd></div>
          <div><dt>{plural(confirmed, "potwierdzone wdrożenie", "potwierdzone wdrożenia", "potwierdzonych wdrożeń")}</dt><dd>{confirmed}</dd></div>
          <div><dt>województw</dt><dd>16</dd></div>
        </dl>}
      </div>
      <aside className="home-examples" aria-labelledby="examples-title">
        <h2 id="examples-title">O co możesz zapytać</h2>
        <ul>{examples.map(text => <li key={text}><Link href={`/rozmowa?pytanie=${encodeURIComponent(text)}`}><MessagesSquare aria-hidden={true} size={18} /><span>{text}</span></Link></li>)}</ul>
        <Link className="home-examples-link" href="/rozmowa?nowa=1">Zadaj własne pytanie<ArrowRight aria-hidden="true" size={16} /></Link>
      </aside>
    </section>

    <section className="home-section" aria-labelledby="areas-title">
      <h2 id="areas-title">Trzy obszary innowacji</h2>
      <ul className="home-entries">{areas.map(({ id, icon: Icon, text }, index) => <li key={id}>
        <Link className="home-entry" href={catalog({ area: id })}>
          <span className="entry-icon"><Icon aria-hidden={true} size={22} /></span>
          <span className="home-entry-title">{innovationAreas[id]}</span>
          <span className="home-entry-text">{text}</span>
          <span className="entry-more">{byArea[index] !== undefined ? `Zobacz ${byArea[index]} ${plural(byArea[index], "rozwiązanie", "rozwiązania", "rozwiązań")}` : "Zobacz rozwiązania"}<ArrowRight aria-hidden="true" size={16} /></span>
        </Link>
      </li>)}</ul>
    </section>

    <section className="home-section home-region" aria-labelledby="region-title">
      <h2 id="region-title">Innowacje z Podkarpacia</h2>
      <p>Radar obejmuje całą Polskę, a PCI prowadzi go dla województwa podkarpackiego: od regionalnej e-administracji po program robotyki w szkołach podstawowych.</p>
      <Link className="home-examples-link" href={catalog({ region: "Podkarpackie" })}>
        {podkarpackie !== undefined ? `Zobacz ${podkarpackie} ${plural(podkarpackie, "rozwiązanie", "rozwiązania", "rozwiązań")} z Podkarpacia` : "Zobacz rozwiązania z Podkarpacia"}<ArrowRight aria-hidden="true" size={16} />
      </Link>
    </section>

    {taxonomy && <section className="home-section" aria-labelledby="criteria-title">
      <h2 id="criteria-title">Jak oceniamy</h2>
      <p className="home-section-lead">Każda karta ma ocenę 1-5 w każdym kryterium. Przy ocenie widać, czy to fakt potwierdzony źródłem, czy szacunek do sprawdzenia.</p>
      <dl className="home-criteria">{Object.values(taxonomy.criteria).map(([name, meaning]) => <div key={name}><dt>{name}</dt><dd>{meaning}</dd></div>)}</dl>
    </section>}

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
