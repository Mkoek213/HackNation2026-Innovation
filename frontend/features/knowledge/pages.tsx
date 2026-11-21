"use client";

import { useState } from "react";
import { Search } from "@/components/ui/icons";
import { Button } from "@/components/ui/button";
import { getCatalog, getTaxonomy, innovationAreas, type Innovation } from "./api";
import { CompareInnovations, InnovationGrid } from "./innovations";
import { useLoad } from "./use-load";

function Status({ data, what }: { data: unknown; what: string }) {
  if (data === null) return <p className="page-status" role="status">Wczytywanie {what}…</p>;
  if (data === false) return <p className="form-error" role="alert">Nie udało się wczytać {what}. Odśwież stronę, aby spróbować ponownie.</p>;
  return null;
}

const pageSize = 24;
const defaults = { q: "", category: "", area: "", region: "", maturity: "", min_credibility: "", confirmed_only: "" };

/** `preset` comes from the URL (?area=…, ?region=…, ?q=…), e.g. links on the home page. */
export function InnovationsPage({ preset = {} }: { preset?: Record<string, string | string[] | undefined> }) {
  const taxonomy = useLoad(getTaxonomy, "taxonomy");
  const initial = Object.fromEntries(Object.keys(defaults).flatMap(name =>
    typeof preset[name] === "string" ? [[name, (preset[name] as string).slice(0, 200)]] : [])) as Partial<typeof defaults>;
  const [query, setQuery] = useState(initial.q ?? "");
  const [filters, setFilters] = useState({ ...defaults, ...initial });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Innovation[]>([]);
  const [compare, setCompare] = useState(false);
  const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  params.set("offset", String(offset));
  params.set("limit", String(pageSize));
  const key = params.toString();
  const results = useLoad(() => getCatalog(key), key);
  const regionParams = filters.confirmed_only ? "limit=1&confirmed_only=true" : "limit=1";
  const regionPage = useLoad(() => getCatalog(regionParams), regionParams);
  const regions = (regionPage ? regionPage.regions : (filters.region ? [filters.region] : [])).toSorted((a, b) => a.localeCompare(b, "pl"));

  function setFilter(name: keyof typeof defaults, value: string) {
    setFilters(current => ({
      ...current, [name]: value,
      ...(name === "confirmed_only" ? { region: "" } : {}),
    }));
    setOffset(0);
  }

  function toggle(item: Innovation) {
    setSelected(items => items.some(entry => entry.id === item.id)
      ? items.filter(entry => entry.id !== item.id)
      : [...items.slice(0, 1), item]);
  }
  return <>
    <header className="page-intro">
      <h1>Baza innowacji</h1>
      <p>Znajdź polskie rozwiązania, sprawdź dowody ich zastosowania i oceń, czy sprawdzą się w Twojej instytucji.</p>
    </header>
    {taxonomy === false && <Status data={false} what="sektorów" />}
    {taxonomy && <div className="filter-bar">
      <form className="flex flex-wrap items-center gap-2" onSubmit={event => { event.preventDefault(); setFilter("q", query.trim()); }}>
        <label className="search-field grow">
          <Search aria-hidden="true" size={18} />
          <span className="sr-only">Szukaj innowacji</span>
          <input type="search" maxLength={200} placeholder="Np. płatności w urzędzie" value={query} onChange={e => setQuery(e.target.value)} />
        </label>
        <Button type="submit">Szukaj</Button>
      </form>
      <div className="chip-row">
        {([
          ["area", "Obszar", Object.entries(innovationAreas)],
          ["region", "Województwo", regions.map(region => [region, region])],
          ["maturity", "Poziom wdrożenia", Object.entries(taxonomy.maturity)],
          ["min_credibility", "Wiarygodność", [["3", "co najmniej 3/5"], ["4", "co najmniej 4/5"], ["5", "5/5"]]],
          ["category", "Sektor", Object.entries(taxonomy.sectors)],
        ] as const).map(([name, label, options]) =>
          <label key={name} className="field-block">{label}
            <select className="chip" value={filters[name]} onChange={e => setFilter(name, e.target.value)}>
              <option value="">Wszystkie</option>
              {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </label>
        )}
      </div>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={Boolean(filters.confirmed_only)} onChange={e => setFilter("confirmed_only", e.target.checked ? "true" : "")} />
        Tylko potwierdzone wdrożenia
      </label>
    </div>}
    {selected.length > 0 && <div className="flex flex-wrap items-center gap-2">
      <span role="status">Wybrano {selected.length} z 2</span>
      {selected.map(item => <Button key={item.id} size="sm" variant="outline" onClick={() => toggle(item)}>
        Usuń: {item.title}
      </Button>)}
      <Button disabled={selected.length !== 2} onClick={() => setCompare(true)}>Porównaj rozwiązania</Button>
    </div>}
    {compare && taxonomy && <CompareInnovations innovations={selected} taxonomy={taxonomy} onClose={() => setCompare(false)} />}
    <Status data={results} what="innowacji" />
    {results && taxonomy && <>
      <p className="result-count" role="status">Wyniki: {results.total}</p>
      {results.items.length > 0 ? <InnovationGrid innovations={results.items} taxonomy={taxonomy} selected={selected} onToggle={toggle} />
        : <p className="empty-state">Brak innowacji dla wybranych filtrów.</p>}
      {results.total > pageSize && <nav aria-label="Strony wyników" className="flex flex-wrap items-center gap-3">
        <Button variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - pageSize)}>Poprzednia</Button>
        <span>Strona {offset / pageSize + 1} z {Math.ceil(results.total / pageSize)}</span>
        <Button variant="outline" disabled={offset + pageSize >= results.total} onClick={() => setOffset(offset + pageSize)}>Następna</Button>
      </nav>}
    </>}
  </>;
}
