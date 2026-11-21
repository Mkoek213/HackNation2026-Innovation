"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api, documentLink, Evidence, Innovation, safeLink } from "./api";

export function Sources({ innovation, onClose }: { innovation: Innovation; onClose: () => void }) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [documents, setDocuments] = useState<Evidence[]>([]);
  const [detailError, setDetailError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ documents: { id: string; filename: string; content_type: string; download_url: string }[] }>(`api/v1/knowledge/innovations/${encodeURIComponent(innovation.id)}`)
      .then(detail => { if (active) setDocuments(detail.documents.map(doc => ({
        text: "", source_file: doc.filename, page_start: null, page_end: null,
        document_id: doc.id, document_url: doc.download_url, content_type: doc.content_type,
      }))); })
      .catch(() => { if (active) setDetailError("Nie udało się wczytać aktualnej listy dokumentów. Zapisane fragmenty pozostają dostępne."); });
    return () => { active = false; };
  }, [innovation.id]);
  const evidence = [...innovation.evidence, ...documents.filter(doc => !innovation.evidence.some(e => e.document_id === doc.document_id))];
  const source = safeLink(innovation.source_url);
  const video = safeLink(innovation.video_url);
  const url = selected && documentLink(selected);
  const pdf = url && selected?.content_type === "application/pdf";
  return <Dialog open onClose={onClose} title={innovation.title}>
    <p>{innovation.solution || "Brak krótkiego opisu w źródłach."}</p>
    {innovation.fit_reason && <><h3>Dlaczego pasuje</h3><p>{innovation.fit_reason}</p></>}
    {innovation.limitations?.length ? <><h3>Ograniczenia i niewiadome</h3><ul className="limitations">{innovation.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul></> : null}
    <h3>Źródła</h3>
    <div className="source-list">{evidence.map((e, i) => <Button variant="outline" key={i} onClick={() => setSelected(e)} aria-pressed={selected === e}>
      {e.source_file || `Fragment źródła ${i + 1}`}{e.page_start ? `, s. ${e.page_start}${e.page_end && e.page_end !== e.page_start ? `–${e.page_end}` : ""}` : ""}
    </Button>)}</div>
    {detailError && <p role="status">{detailError}</p>}
    {!evidence.length && <p>Brak fragmentów dokumentów dla tej propozycji.</p>}
    {source && <p><a href={source} target="_blank" rel="noopener noreferrer">Otwórz stronę źródłową<span className="sr-only"> (otwiera się w nowej karcie)</span></a></p>}
    {video && <p><a href={video} target="_blank" rel="noopener noreferrer">Otwórz materiał wideo<span className="sr-only"> (otwiera się w nowej karcie)</span></a></p>}
    {selected && <section aria-label="Wybrane źródło">{selected.text ? <blockquote>{selected.text}</blockquote> : <p>Dokument źródłowy bez wskazanego fragmentu. Plik może nie mieć warstwy tekstowej.</p>}
      {selected.page_start && <p>Strona {selected.page_start}{selected.page_end && selected.page_end !== selected.page_start ? `–${selected.page_end}` : ""}</p>}
      {url ? <><p><a href={`${url}${pdf && selected.page_start ? `#page=${selected.page_start}` : ""}`} target="_blank" rel="noopener noreferrer">{pdf ? "Otwórz PDF w nowej karcie" : "Pobierz dokument"}{!pdf && <span className="sr-only"> (otwiera się w nowej karcie)</span>}</a></p>
        {pdf ? <><p className="pdf-help">Jeśli podgląd nie działa, otwórz PDF w nowej karcie. Obsługa wskazanej strony zależy od przeglądarki.</p><object className="pdf-preview" data={`${url}#page=${selected.page_start || 1}`} type="application/pdf" aria-label={`PDF: ${selected.source_file || innovation.title}`}><p>Podgląd niedostępny. <a href={url} target="_blank" rel="noopener noreferrer">Otwórz PDF<span className="sr-only"> (otwiera się w nowej karcie)</span></a></p></object></> : <p>Ten dokument nie jest plikiem PDF.</p>}
      </> : <p>Nie można jednoznacznie powiązać tego fragmentu z dostępnym dokumentem. {source && <a href={source} target="_blank" rel="noopener noreferrer">Sprawdź stronę źródłową<span className="sr-only"> (otwiera się w nowej karcie)</span></a>}</p>}
    </section>}
  </Dialog>;
}
