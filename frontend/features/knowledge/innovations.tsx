"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Building, ExternalLink, FileText, Play } from "@/components/ui/icons";
import { recordVisit } from "@/features/workspace";
import { getSimilar, innovationAreas, type Assessment, type AssessmentNote, type Innovation, type Taxonomy } from "./api";
import { AREAS, areaOf } from "./category-areas";
import { useLoad } from "./use-load";

function youtubeId(url: string | null) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    const id = parsed.hostname.endsWith("youtu.be") ? parsed.pathname.slice(1) : parsed.searchParams.get("v");
    return id && /^[\w-]{6,20}$/.test(id) ? id : null;
  } catch { return null; }
}
function httpLink(url: string | null) {
  try { return url && ["https:", "http:"].includes(new URL(url).protocol) ? url : null; } catch { return null; }
}
const DOCUMENT_URL = /^\/api\/v1\/knowledge\/innovations\/[a-z0-9-]+\/documents\/[a-f0-9]{32}$/;

export function InnovationGrid({ innovations, taxonomy, selected, onToggle }: {
  innovations: Innovation[]; taxonomy: Taxonomy; selected: Innovation[]; onToggle: (item: Innovation) => void;
}) {
  const labels = taxonomy.sectors;
  const [open, setOpen] = useState<Innovation | null>(null);
  function show(item: Innovation) {
    setOpen(item);
    void recordVisit(`/_radar/karta/${item.id}`); // anonymous catalog analytics, see Analityka
  }
  const shown = AREAS.filter(area => innovations.some(item => areaOf(item.area) === area.id));
  return <>
    {shown.length > 1 && <ul className="area-legend" aria-label="Kolor paska karty oznacza obszar zastosowania">
      {shown.map(area => <li key={area.id} data-area={area.id}>{area.label}</li>)}
    </ul>}
    <ul className="innovation-grid">
      {innovations.map(item => <li key={item.id}>
        <button type="button" className="innovation-card" data-area={areaOf(item.area)} onClick={() => show(item)} aria-haspopup="dialog">
          <span className="innovation-category">{item.area ? innovationAreas[item.area] : labels[item.primary_category] ?? item.primary_category}</span>
          <span className="innovation-title">{item.title}</span>
          <span className="innovation-solution">{item.assessment.summary || item.card.solution || item.card.problem}</span>
          <span className="innovation-meta">
            {item.institution && <span><Building aria-hidden="true" size={14} />{item.institution}</span>}
            {item.maturity && <span>{taxonomy.maturity[item.maturity] ?? item.maturity}</span>}
            {item.verification === "kandydat" && <span>Do weryfikacji</span>}
            {youtubeId(item.video_url) && <span><Play aria-hidden="true" size={14} />Film</span>}
            {item.documents.length > 0 && <span><FileText aria-hidden="true" size={14} />Dokumenty: {item.documents.length}</span>}
          </span>
        </button>
        <label className="flex items-center gap-2 p-2">
          <input type="checkbox" checked={selected.some(entry => entry.id === item.id)}
            disabled={selected.length === 2 && !selected.some(entry => entry.id === item.id)}
            aria-label={`Wybierz do porównania: ${item.title}`}
            onChange={() => onToggle(item)} />
          Wybierz do porównania
        </label>
      </li>)}
    </ul>
    {open && <InnovationDialog key={open.id} innovation={open} taxonomy={taxonomy} onClose={() => setOpen(null)} onOpen={show} />}
  </>;
}

const date = new Intl.DateTimeFormat("pl-PL", { dateStyle: "long" });

function AssessmentRows({ assessment, taxonomy }: { assessment: Assessment; taxonomy: Taxonomy }) {
  const label = (key: keyof Taxonomy["criteria"]) => taxonomy.criteria[key]?.[0] ?? key;
  const criteria: [string, AssessmentNote | null, string][] = [
    [label("implementation"), assessment.implementation, ""],
    ...(assessment.trl !== null ? [[label("trl"), assessment.trl_basis, `TRL ${assessment.trl}/9`] as [string, AssessmentNote | null, string]] : []),
    [label("novelty"), assessment.novelty, ""],
    [label("transfer"), assessment.transfer, ""],
    [label("credibility"), assessment.credibility, ""],
  ];
  return <dl className="innovation-facts assessment-rows">
    {criteria.map(([term, note, extra]) => {
      const evidence = httpLink(note?.source_url ?? null);
      const score = extra || (note?.score ? `${note.score}/5` : "");
      return <div key={term}><dt>{term}</dt><dd>
        {note ? <>
          <span className="assessment-head">
            {score && <span className="score-badge">{score}</span>}
            <span className="basis-badge" data-basis={note.basis}>{note.basis === "potwierdzone" ? "Potwierdzone" : "Szacunek"}</span>
          </span>
          {note.rationale}
          {evidence && <> <a href={evidence} target="_blank" rel="noopener noreferrer">Źródło oceny<span className="sr-only"> (otwiera się w nowej karcie)</span></a></>}
        </> : "Brak oceny"}
      </dd></div>;
    })}
  </dl>;
}

function Recommendation({ assessment, taxonomy, level = "h3" }: { assessment: Assessment; taxonomy: Taxonomy; level?: "h3" | "h4" }) {
  const Heading = level;
  const { path, recipients, measures } = assessment;
  if (!path && !recipients.length && !measures.length && !assessment.next_step) return null;
  return <section className="recommendation">
    <Heading>Potencjalni odbiorcy i ścieżka</Heading>
    {path && <p><strong>{taxonomy.paths[path] ?? path}</strong>{assessment.path_rationale && <> · {assessment.path_rationale}</>}</p>}
    {recipients.length > 0 && <ul>{recipients.map(r => <li key={r.audience}><strong>{taxonomy.audiences[r.audience] ?? r.audience}</strong> · {r.why}</li>)}</ul>}
    {assessment.next_step && <p><strong>Pierwszy krok</strong> · {assessment.next_step}</p>}
    {measures.length > 0 && <>
      <p className="recommendation-label">Jak mierzyć efekt</p>
      <ul>{measures.map(m => <li key={m}>{m}</li>)}</ul>
    </>}
  </section>;
}

export function AssessmentMethod({ taxonomy, assessment }: { taxonomy: Taxonomy; assessment?: Assessment }) {
  return <details className="assessment-method">
    <summary>Jak oceniamy</summary>
    <p>Każde kryterium ma ocenę 1-5 i oznaczenie: <strong>Potwierdzone</strong> (fakt z podanego źródła) albo <strong>Szacunek</strong> (wniosek z opisu, wymaga sprawdzenia).
      Wiarygodność liczą stałe reguły, pozostałe kryteria, odbiorców, ścieżkę i mierniki proponuje model AI na podstawie tekstu karty.
      Redakcja PCI może każdą ocenę poprawić; poprawki nie są nadpisywane.</p>
    <dl>{Object.values(taxonomy.criteria).map(([name, meaning]) => <div key={name}><dt>{name}</dt><dd>{meaning}</dd></div>)}</dl>
    <p className="source-note">Wersja kryteriów: {taxonomy.criteria_version}
      {assessment?.assessed_at && <>, ocena z {date.format(new Date(assessment.assessed_at))}</>}.</p>
  </details>;
}

export function CompareInnovations({ innovations, taxonomy, onClose }: {
  innovations: Innovation[]; taxonomy: Taxonomy; onClose: () => void;
}) {
  const pair = innovations.map(item => `„${item.title}” (${item.id})`).join(" i ");
  const question = `Porównaj ${pair} dla mojej instytucji. Jaką potrzebę obsługuje każde rozwiązanie? Podaj źródła, warunki wdrożenia i miernik.`;
  return <Dialog open onClose={onClose} title="Porównanie innowacji" className="innovation-modal">
    <div className="grid gap-4 md:grid-cols-2">
      {innovations.map(item => <section key={item.id}>
        <h3>{item.title}</h3>
        <p className="source-note">{item.verification === "potwierdzona" ? "Potwierdzone użycie" : "Kandydat do weryfikacji"}
          {item.maturity && <> · {taxonomy.maturity[item.maturity]}</>}</p>
        <p>{item.assessment.summary || item.card.solution}</p>
        <AssessmentRows assessment={item.assessment} taxonomy={taxonomy} />
        <Recommendation assessment={item.assessment} taxonomy={taxonomy} level="h4" />
      </section>)}
    </div>
    <AssessmentMethod taxonomy={taxonomy} />
    <Button variant="outline" nativeButton={false} render={<Link href={`/rozmowa?pytanie=${encodeURIComponent(question)}`} />}>
      Doprecyzuj w rozmowie
    </Button>
  </Dialog>;
}

function Similar({ innovation, taxonomy, onOpen }: { innovation: Innovation; taxonomy: Taxonomy; onOpen: (item: Innovation) => void }) {
  const similar = useLoad(() => getSimilar(innovation.id), innovation.id);
  if (!similar || similar.length === 0) return null;
  return <section className="similar">
    <h3>Podobne rozwiązania</h3>
    <p className="source-note">Sprawdź je, zanim zaczniesz własny projekt: ktoś mógł już rozwiązać ten sam problem.</p>
    <ul>{similar.map(item => <li key={item.id}>
      <button type="button" onClick={() => onOpen(item)}>
        <span className="similar-title">{item.title}</span>
        <span className="similar-meta">{[item.institution, item.region, item.maturity && taxonomy.maturity[item.maturity]].filter(Boolean).join(" · ")}</span>
      </button>
    </li>)}</ul>
  </section>;
}

function InnovationDialog({ innovation, taxonomy, onClose, onOpen }: {
  innovation: Innovation; taxonomy: Taxonomy; onClose: () => void; onOpen: (item: Innovation) => void;
}) {
  const labels = taxonomy.sectors;
  const video = youtubeId(innovation.video_url);
  const source = httpLink(innovation.source_url);
  const { card } = innovation;
  const assessment = innovation.assessment;
  const sections: [string, string][] = [
    ["Jaki problem rozwiązuje", card.problem],
    ["W skrócie", assessment.summary],
    ["Na czym polega", card.solution],
    ["Co jest nowego", card.novelty],
    ["Kto może skorzystać lub wdrożyć", card.target_users],
    ["Stan zaawansowania i dowody", assessment.implementation ? "" : card.evidence],
  ];
  const institution = [innovation.institution, innovation.institution_type && taxonomy.institution_types[innovation.institution_type]].filter(Boolean).join(" · ");
  const facts: [string, string][] = [
    ["Weryfikacja", innovation.verification === "potwierdzona" ? "Potwierdzone użycie" : "Kandydat do weryfikacji"],
    ["Obszar", innovation.area ? innovationAreas[innovation.area] : ""],
    ["Województwo", innovation.region ?? ""],
    ["Rodzaj innowacji", innovation.innovation_type ? taxonomy.innovation_types[innovation.innovation_type] ?? innovation.innovation_type : ""],
    ["Instytucja", institution],
    ["Poziom wdrożenia", innovation.maturity ? taxonomy.maturity[innovation.maturity] ?? innovation.maturity : ""],
    ["Twórcy", innovation.authors.map(a => a.affiliation ? `${a.name} (${a.affiliation})` : a.name).join(", ")],
  ];
  return <Dialog open onClose={onClose} title={innovation.title} className="innovation-modal">
    <p className="innovation-tags">{innovation.categories.map(c => <span key={c}>{labels[c] ?? c}</span>)}</p>
    {video && <>
      <div className="video-frame">
        <iframe src={`https://www.youtube-nocookie.com/embed/${video}?cc_load_policy=1&hl=pl&cc_lang_pref=pl`} title={`Film o innowacji ${innovation.title}`} loading="lazy"
          allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" />
      </div>
      <p className="pdf-help">Napisy włączają się w odtwarzaczu, jeśli film je ma. <a href={`https://www.youtube.com/watch?v=${video}`} target="_blank" rel="noopener noreferrer">Otwórz film w YouTube<span className="sr-only"> (otwiera się w nowej karcie)</span></a></p>
    </>}
    {facts.some(([, value]) => value) && <dl className="innovation-facts">
      {facts.filter(([, value]) => value).map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}
    </dl>}
    {sections.filter(([, text]) => text).map(([heading, text]) => <section key={heading}><h3>{heading}</h3><p>{text}</p></section>)}
    <section>
      <h3>Ocena potencjału</h3>
      <AssessmentRows assessment={assessment} taxonomy={taxonomy} />
      <AssessmentMethod taxonomy={taxonomy} assessment={assessment} />
    </section>
    <Recommendation assessment={assessment} taxonomy={taxonomy} />
    {innovation.documents.length > 0 && <section>
      <h3>Dokumenty</h3>
      <ul className="document-list">
        {innovation.documents.filter(d => DOCUMENT_URL.test(d.download_url)).map(d => <li key={d.id}>
          <a href={`/api/backend${d.download_url}`} target="_blank" rel="noopener noreferrer"><FileText aria-hidden="true" size={16} />{d.filename}<span className="sr-only"> (otwiera się w nowej karcie)</span></a>
        </li>)}
      </ul>
    </section>}
    {(source || innovation.source_name) && <p className="source-note">
      Źródło: {source
        ? <a href={source} target="_blank" rel="noopener noreferrer">{innovation.source_name ?? "opis u źródła"}<ExternalLink aria-hidden="true" size={14} /><span className="sr-only"> (otwiera się w nowej karcie)</span></a>
        : innovation.source_name}
      {innovation.imported_at && <>, dane pobrane {date.format(new Date(innovation.imported_at))}</>}
      {innovation.checked_at && <>, sprawdzono {date.format(new Date(innovation.checked_at))}</>}
    </p>}
    <Similar innovation={innovation} taxonomy={taxonomy} onOpen={onOpen} />
    <p><Link href={`/rozmowa?pytanie=${encodeURIComponent(`Porównaj „${innovation.title}” (${innovation.id}) z innym rozwiązaniem dla podobnej potrzeby. Podaj źródła, warunki wdrożenia i następny krok.`)}`}>Porównaj w rozmowie</Link></p>
  </Dialog>;
}
