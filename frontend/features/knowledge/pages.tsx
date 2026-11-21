"use client";

import { useMemo, useState } from "react";
import { Search } from "@/components/ui/icons";
import { getInnovations, getTaxonomy } from "./api";
import { InnovationGrid } from "./innovations";
import { useLoad } from "./use-load";

function Status({ data, what }: { data: unknown; what: string }) {
  if (data === null) return <p className="page-status" role="status">Wczytywanie {what}…</p>;
  if (data === false) return <p className="form-error" role="alert">Nie udało się wczytać {what}. Odśwież stronę, aby spróbować ponownie.</p>;
  return null;
}

export function InnovationsPage() {
  const innovations = useLoad(getInnovations, "innovations");
  const taxonomy = useLoad(getTaxonomy, "taxonomy");
  const labels = taxonomy ? taxonomy.sectors : null;
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const used = useMemo(() => innovations && labels ? Object.keys(labels).filter(c => innovations.some(i => i.categories.includes(c))) : [], [innovations, labels]);
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("pl");
    return (innovations || []).filter(i => (!category || i.categories.includes(category))
      && (!needle || [i.title, i.institution ?? "", i.card.solution, i.card.problem, i.card.novelty, i.card.target_users].join(" ").toLocaleLowerCase("pl").includes(needle)));
  }, [innovations, category, query]);
  return <>
    <header className="page-intro">
      <h1>Baza innowacji</h1>
      <p>Innowacje ze szkół, uczelni, samorządów i innych instytucji publicznych, opisane według jednego schematu. Wyszukaj według tematu, instytucji albo sektora.</p>
    </header>
    <Status data={innovations} what="innowacji" />
    {taxonomy === false && <Status data={false} what="sektorów" />}
    {innovations && taxonomy && labels && <>
      <div className="filter-bar">
        <label className="search-field">
          <Search aria-hidden="true" size={18} />
          <span className="sr-only">Szukaj innowacji</span>
          <input type="search" placeholder="Szukaj, np. drony, powietrze, Politechnika Rzeszowska" value={query} onChange={e => setQuery(e.target.value)} />
        </label>
        <div className="chip-row" role="group" aria-label="Filtruj według sektora">
          <button type="button" className="chip" aria-pressed={!category} onClick={() => setCategory("")}>Wszystkie</button>
          {used.map(c => <button key={c} type="button" className="chip" aria-pressed={category === c} onClick={() => setCategory(c)}>{labels[c]}</button>)}
        </div>
      </div>
      <p className="result-count" role="status">{visible.length === 1 ? "1 innowacja" : `Innowacje: ${visible.length}`}</p>
      {visible.length ? <InnovationGrid innovations={visible} taxonomy={taxonomy} /> : <p className="empty-state">Brak innowacji dla wybranych filtrów.</p>}
    </>}
  </>;
}
