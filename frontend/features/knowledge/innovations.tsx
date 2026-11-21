"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Building, ExternalLink, FileText, Play } from "@/components/ui/icons";
import { ApplyAsTester } from "@/features/tester";
import type { Innovation, Taxonomy } from "./api";
import { AREAS, areaOf } from "./category-areas";

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

export function InnovationGrid({ innovations, taxonomy }: { innovations: Innovation[]; taxonomy: Taxonomy }) {
  const labels = taxonomy.sectors;
  const [open, setOpen] = useState<Innovation | null>(null);
  const shown = AREAS.filter(area => innovations.some(item => areaOf(item.primary_category) === area.id));
  return <>
    {shown.length > 1 && <ul className="area-legend" aria-label="Kolor paska karty oznacza obszar">
      {shown.map(area => <li key={area.id} data-area={area.id}>{area.label}</li>)}
    </ul>}
    <ul className="innovation-grid">
      {innovations.map(item => <li key={item.id}>
        <button type="button" className="innovation-card" data-area={areaOf(item.primary_category)} onClick={() => setOpen(item)} aria-haspopup="dialog">
          <span className="innovation-category">{labels[item.primary_category] ?? item.primary_category}</span>
          <span className="innovation-title">{item.title}</span>
          <span className="innovation-solution">{item.card.solution || item.card.problem}</span>
          <span className="innovation-meta">
            {item.institution && <span><Building aria-hidden="true" size={14} />{item.institution}</span>}
            {item.maturity && <span>{taxonomy.maturity[item.maturity] ?? item.maturity}</span>}
            {youtubeId(item.video_url) && <span><Play aria-hidden="true" size={14} />Film</span>}
            {item.documents.length > 0 && <span><FileText aria-hidden="true" size={14} />Dokumenty: {item.documents.length}</span>}
          </span>
        </button>
      </li>)}
    </ul>
    {open && <InnovationDialog innovation={open} taxonomy={taxonomy} onClose={() => setOpen(null)} />}
  </>;
}

const date = new Intl.DateTimeFormat("pl-PL", { dateStyle: "long" });

function InnovationDialog({ innovation, taxonomy, onClose }: { innovation: Innovation; taxonomy: Taxonomy; onClose: () => void }) {
  const labels = taxonomy.sectors;
  const video = youtubeId(innovation.video_url);
  const source = httpLink(innovation.source_url);
  const { card } = innovation;
  const sections: [string, string][] = [
    ["Jaki problem rozwiązuje", card.problem],
    ["Na czym polega", card.solution],
    ["Co jest nowego", card.novelty],
    ["Kto może skorzystać lub wdrożyć", card.target_users],
    ["Stan zaawansowania i dowody", card.evidence],
  ];
  const institution = [innovation.institution, innovation.institution_type && taxonomy.institution_types[innovation.institution_type]].filter(Boolean).join(" · ");
  const facts: [string, string][] = [
    ["Rodzaj innowacji", innovation.innovation_type ? taxonomy.innovation_types[innovation.innovation_type] ?? innovation.innovation_type : ""],
    ["Instytucja", institution],
    ["Etap rozwoju", innovation.maturity ? taxonomy.maturity[innovation.maturity] ?? innovation.maturity : ""],
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
    </p>}
    <ApplyAsTester innovationId={innovation.id} innovationTitle={innovation.title} />
  </Dialog>;
}
