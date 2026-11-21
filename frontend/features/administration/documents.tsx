"use client";

import { useEffect, useRef, useState } from "react";
import { Tabs } from "@base-ui/react/tabs";
import { api, ApiError } from "@/features/workspace";
import { innovationAreas, type Assessment, type AssessmentNote, type Discovery } from "@/features/knowledge";
import { Button } from "@/components/ui/button";
import { FileText } from "@/components/ui/icons";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import styles from "./administration.module.css";

type Card = { problem: string; solution: string; novelty: string; target_users: string; evidence: string };
type Author = { name: string; affiliation: string | null };
type Taxonomy = { sectors: Record<string, string>; innovation_types: Record<string, string>; institution_types: Record<string, string>; maturity: Record<string, string> };
// Descriptive axes and provenance; authors and import date come from importers and are kept unchanged on edit.
type Profile = {
  innovation_type: string | null; institution_type: string | null; institution: string | null; maturity: string | null;
  source_name: string | null; authors: Author[]; imported_at: string | null;
} & Discovery;
type StoredDocument = { id: string; filename: string; download_url: string };
type Innovation = {
  id: string; title: string; primary_category: string; categories: string[];
  source_url: string | null; video_url: string | null; card: Card; files: string[]; documents: StoredDocument[];
} & Profile;
type IngestResult = { innovation_id: string; chunks: number; files: string[]; skipped_files: string[] };
type Draft = {
  title: string; source_url: string | null; card: Card;
  primary_category: string | null; categories: string[];
  innovation_type: string | null; institution_type: string | null; institution: string | null; maturity: string | null;
  category_status: "completed" | "uncertain" | "unavailable";
  card_status: "completed" | "unavailable";
  files: string[]; skipped_files: string[];
};
type CardForm = { title: string; primary: string; extra: string[]; sourceUrl: string; card: Card; profile: Profile };
type Saved = { title: string; id: string; ingest: IngestResult | null };
type Mode = "create" | "edit";

const emptyCard: Card = { problem: "", solution: "", novelty: "", target_users: "", evidence: "" };
const emptyAssessment: Assessment = {
  implementation: null, novelty: null, transfer: null, credibility: null, trl: null, trl_basis: null, next_step: "",
  summary: "", recipients: [], path: null, path_rationale: "", measures: [], criteria_version: "", assessed_at: null,
};
const emptyProfile: Profile = {
  innovation_type: null, institution_type: null, institution: null, maturity: null, source_name: null, authors: [], imported_at: null,
  area: null, region: null, checked_at: null, verification: "kandydat", assessment: emptyAssessment,
};
const emptyForm: CardForm = { title: "", primary: "", extra: [], sourceUrl: "", card: emptyCard, profile: emptyProfile };
const cardFields: { key: keyof Card; label: string }[] = [
  { key: "problem", label: "Jaki problem rozwiązuje?" },
  { key: "solution", label: "Na czym polega rozwiązanie?" },
  { key: "novelty", label: "Co jest nowego w porównaniu z istniejącymi rozwiązaniami?" },
  { key: "target_users", label: "Kto może z niej skorzystać lub ją wdrożyć?" },
  { key: "evidence", label: "Stan zaawansowania i dowody działania" },
];
const profileAxes: { key: "innovation_type" | "institution_type" | "maturity"; axis: Exclude<keyof Taxonomy, "sectors">; label: string }[] = [
  { key: "innovation_type", axis: "innovation_types", label: "Rodzaj innowacji" },
  { key: "institution_type", axis: "institution_types", label: "Typ instytucji źródłowej" },
  { key: "maturity", axis: "maturity", label: "Poziom wdrożenia" },
];
const fileTypes = ".pdf,.docx,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip";
const documentUrl = /^\/api\/v1\/knowledge\/innovations\/[a-z0-9-]+\/documents\/[a-f0-9]{32}$/;
const uploadTimeoutMs = 610000;

function slugify(text: string) {
  return text.toLowerCase().replaceAll("ł", "l").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
}

function formOf(innovation: Innovation): CardForm {
  return {
    title: innovation.title, primary: innovation.primary_category,
    extra: innovation.categories.filter(category => category !== innovation.primary_category),
    sourceUrl: innovation.source_url ?? "", card: { ...emptyCard, ...innovation.card },
    profile: {
      innovation_type: innovation.innovation_type, institution_type: innovation.institution_type, institution: innovation.institution,
      maturity: innovation.maturity, source_name: innovation.source_name, authors: innovation.authors ?? [], imported_at: innovation.imported_at,
      area: innovation.area, region: innovation.region, checked_at: innovation.checked_at,
      verification: innovation.verification, assessment: innovation.assessment,
    },
  };
}

function metaOf(form: CardForm, videoUrl: string | null) {
  const assessment = { ...form.profile.assessment };
  for (const key of ["implementation", "novelty", "transfer", "credibility", "trl_basis"] as const) {
    const note = assessment[key];
    assessment[key] = note?.rationale.trim() ? { ...note, rationale: note.rationale.trim() } : null;
  }
  return {
    title: form.title.trim(), primary_category: form.primary,
    categories: [form.primary, ...form.extra.filter(category => category !== form.primary)],
    source_url: form.sourceUrl.trim() || null, video_url: videoUrl, card: form.card,
    ...form.profile, institution: form.profile.institution?.trim() || null, source_name: form.profile.source_name?.trim() || null,
    region: form.profile.region?.trim() || null, assessment,
  };
}

function draftError(cause: unknown) {
  if (!(cause instanceof ApiError)) return "Nie udało się odczytać dokumentów. Sprawdź połączenie i uzupełnij kartę ręcznie.";
  if (cause.status === 401) return "Sesja wygasła. Zaloguj się ponownie.";
  if (cause.status === 403) return "Brak uprawnień administratora albo żądanie zostało odrzucone. Odśwież stronę.";
  if (cause.status === 413) return "Plik lub archiwum przekracza dopuszczalny rozmiar.";
  if (cause.status === 422) return "Nie udało się odczytać plików. Sprawdź, czy to PDF lub DOCX z warstwą tekstową, i uzupełnij kartę ręcznie.";
  if (cause.status === 503) return "Odczyt dokumentów jest teraz niedostępny. Uzupełnij kartę ręcznie.";
  return "Nie udało się odczytać dokumentów. Uzupełnij kartę ręcznie.";
}

function saveError(cause: unknown, withFiles: boolean) {
  if (!(cause instanceof ApiError)) return "Nie udało się zapisać innowacji. Sprawdź połączenie i spróbuj ponownie.";
  if (cause.status === 401) return "Sesja wygasła. Zaloguj się ponownie.";
  if (cause.status === 403) return "Brak uprawnień administratora albo żądanie zostało odrzucone. Odśwież stronę.";
  if (cause.status === 404) return "Ta innowacja nie istnieje już w bazie wiedzy. Odśwież stronę.";
  if (cause.status === 413) return "Plik lub archiwum przekracza dopuszczalny rozmiar.";
  if (cause.status === 422) return withFiles ? "Sprawdź dane formularza i pliki. Obsługiwane są dokumenty PDF, DOCX i archiwa ZIP." : "Sprawdź dane formularza.";
  if (cause.status === 503) return "Baza wiedzy jest teraz niedostępna. Spróbuj ponownie później.";
  return "Nie udało się zapisać innowacji. Spróbuj ponownie.";
}

function SaveResult({ saved, verb }: { saved: Saved; verb: string }) {
  const { ingest } = saved;
  return <>
    <p className={styles.resultLine}>{verb} innowację „{saved.title}”.{ingest ? ` Liczba zindeksowanych fragmentów: ${ingest.chunks}.` : ""}</p>
    {ingest && ingest.files.length > 0 && <p className={styles.resultLine}>Zindeksowane pliki: {ingest.files.join(", ")}.</p>}
    {ingest && ingest.skipped_files.length > 0 && <p className={styles.resultWarning}>Pominięte pliki (nieobsługiwany format lub skan bez warstwy tekstowej): {ingest.skipped_files.join(", ")}.</p>}
  </>;
}

// Card fields shared by both flows; the title stays with each flow because creation derives the identifier from it.
function CardFields({ form, onChange, taxonomy, disabled, reading = false }: {
  form: CardForm; onChange: (update: (old: CardForm) => CardForm) => void;
  taxonomy: Taxonomy; disabled: boolean; reading?: boolean;
}) {
  const categories = taxonomy.sectors;
  const setProfile = (patch: Partial<Profile>) => onChange(old => ({ ...old, profile: { ...old.profile, ...patch } }));
  return <>
    <label className="field-block">Sektor główny
      <select className="select" required value={form.primary} onChange={e => { const primary = e.target.value; onChange(old => ({ ...old, primary })); }} disabled={disabled}>
        <option value="" disabled>{reading ? "Odczytuję sektor…" : "Wybierz sektor"}</option>
        {Object.entries(categories).map(([slug, label]) => <option key={slug} value={slug}>{label}</option>)}
      </select>
    </label>
    <fieldset className={styles.categoryList} disabled={disabled}>
      <legend>Dodatkowe sektory</legend>
      {Object.entries(categories).filter(([slug]) => slug !== form.primary).map(([slug, label]) => <label key={slug} className="consent">
        <input type="checkbox" checked={form.extra.includes(slug)}
          onChange={e => { const checked = e.target.checked; onChange(old => ({ ...old, extra: checked ? [...old.extra, slug] : old.extra.filter(c => c !== slug) })); }} />
        <span>{label}</span>
      </label>)}
    </fieldset>
    {profileAxes.map(({ key, axis, label }) => <label key={key} className="field-block">{label}
      <select className="select" value={form.profile[key] ?? ""} onChange={e => setProfile({ [key]: e.target.value || null })} disabled={disabled}>
        <option value="">Nie określono</option>
        {Object.entries(taxonomy[axis]).map(([slug, text]) => <option key={slug} value={slug}>{text}</option>)}
      </select>
    </label>)}
    <AssessmentFields profile={form.profile} onChange={setProfile} disabled={disabled} />
    <label className="field-block">Instytucja, w której powstała
      <Input maxLength={300} value={form.profile.institution ?? ""} onChange={e => setProfile({ institution: e.target.value })} disabled={disabled} placeholder="np. Politechnika Rzeszowska" />
    </label>
    <label className="field-block">Nazwa źródła
      <Input maxLength={200} value={form.profile.source_name ?? ""} onChange={e => setProfile({ source_name: e.target.value })} disabled={disabled} placeholder="np. Urząd Patentowy RP" />
    </label>
    <label className="field-block">Link do źródła
      <Input type="url" maxLength={2000} value={form.sourceUrl} onChange={e => { const sourceUrl = e.target.value; onChange(old => ({ ...old, sourceUrl })); }} disabled={disabled} placeholder="https://" />
    </label>
    {cardFields.map(field => <label key={field.key} className="field-block">{field.label}
      <Textarea maxLength={4000} value={form.card[field.key]} disabled={disabled} className="field-textarea"
        onChange={e => { const value = e.target.value; onChange(old => ({ ...old, card: { ...old.card, [field.key]: value } })); }} />
    </label>)}
  </>;
}

function AssessmentFields({ profile, onChange, disabled }: {
  profile: Profile; onChange: (patch: Partial<Profile>) => void; disabled: boolean;
}) {
  const { assessment } = profile;
  const setAssessment = (patch: Partial<Assessment>) => onChange({ assessment: { ...assessment, ...patch } });
  const criteria = [
    ["implementation", "Etap i dowód zastosowania"], ["novelty", "Nowość"],
    ["transfer", "Możliwość transferu"], ["credibility", "Wiarygodność dowodów"],
  ] as const;
  const rows = assessment.trl === null ? criteria : [...criteria, ["trl_basis", "Podstawa oceny TRL"] as const];
  return <details>
    <summary>Weryfikacja i ocena potencjału</summary>
    <fieldset className={styles.uploadForm} disabled={disabled}>
      <legend className="sr-only">Ocena potencjału</legend>
      <label className="field-block">Obszar zastosowania
        <select className="select" value={profile.area ?? ""} onChange={e => {
          const area = (e.target.value || null) as Discovery["area"];
          onChange({ area, ...(area !== "technologia" ? { assessment: { ...assessment, trl: null, trl_basis: null } } : {}) });
        }}>
          <option value="">Nie określono</option>
          {Object.entries(innovationAreas).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <label className="field-block">Województwo
        <Input maxLength={60} value={profile.region ?? ""} onChange={e => onChange({ region: e.target.value || null })} />
      </label>
      <label className="field-block">Status weryfikacji
        <select className="select" value={profile.verification} onChange={e => onChange({ verification: e.target.value as Discovery["verification"] })}>
          <option value="zgloszone">Zgłoszenie użytkownika (ukryte)</option>
          <option value="kandydat">Kandydat do weryfikacji</option>
          <option value="potwierdzona">Potwierdzone użycie</option>
        </select>
        <span className="field-help">Zgłoszenia użytkowników są ukryte w katalogu i czacie do zmiany statusu. Potwierdzenie wymaga etapu pilotażu lub stosowania oraz uzasadnienia ze źródłem rzeczywistego użycia.</span>
      </label>
      {profile.area === "technologia" && <label className="field-block">TRL (opcjonalnie)
        <Input type="number" min={1} max={9} value={assessment.trl ?? ""} onChange={e => {
          const trl = e.target.value ? Number(e.target.value) : null;
          setAssessment({ trl, ...(trl === null ? { trl_basis: null } : {}) });
        }} />
      </label>}
      {rows.map(([key, label]) => {
        const note = assessment[key] ?? { basis: "szacunek", rationale: "", source_url: null, score: null };
        const setNote = (patch: Partial<AssessmentNote>) => setAssessment({ [key]: { ...note, ...patch } });
        return <fieldset key={key} className={styles.uploadForm}>
          <legend>{label}</legend>
          <label className="field-block">Podstawa oceny
            <select className="select" value={note.basis} onChange={e => setNote({ basis: e.target.value as AssessmentNote["basis"] })}>
              <option value="szacunek">Szacunek</option><option value="potwierdzone">Potwierdzone</option>
            </select>
          </label>
          <label className="field-block">Uzasadnienie
            <Textarea rows={2} maxLength={1200} value={note.rationale} onChange={e => setNote({ rationale: e.target.value })} />
          </label>
          <label className="field-block">URL źródła oceny
            <Input type="url" maxLength={2000} value={note.source_url ?? ""} onChange={e => setNote({ source_url: e.target.value || null })} />
          </label>
        </fieldset>;
      })}
      <label className="field-block">Proponowany następny krok
        <Textarea rows={2} maxLength={1200} value={assessment.next_step} onChange={e => setAssessment({ next_step: e.target.value })} />
      </label>
    </fieldset>
  </details>;
}

function CreateInnovation({ taxonomy, innovations, onSaved, onEdit }: {
  taxonomy: Taxonomy; innovations: Innovation[];
  onSaved: () => Promise<unknown>; onEdit: (id: string) => void;
}) {
  const [form, setForm] = useState<CardForm>(emptyForm);
  const [id, setId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [draftNote, setDraftNote] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Saved | null>(null);
  const draftRequest = useRef(0);
  const titleEdited = useRef(false);
  const idInput = useRef<HTMLInputElement>(null);

  const taken = innovations.find(item => item.id === id);

  async function readFiles(next: File[]) {
    setFiles(next); setSaved(null);
    if (next.length === 0) { draftRequest.current += 1; setReading(false); setDraftNote([]); return; }
    const request = ++draftRequest.current;
    setReading(true); setError(""); setDraftNote([]);
    const body = new FormData();
    for (const file of next) body.append("files", file);
    try {
      const draft = await api<Draft>("api/v1/knowledge/innovations/draft", "POST", body, 180000);
      if (draftRequest.current !== request) return;
      const keepTitle = titleEdited.current;
      if (!keepTitle && draft.title) { setForm(old => ({ ...old, title: draft.title })); if (!idEdited) setId(slugify(draft.title)); }
      if (draft.primary_category) {
        const primary = draft.primary_category;
        setForm(old => ({ ...old, primary, extra: draft.categories.filter(category => category !== primary) }));
      }
      if (draft.card_status === "completed") {
        setForm(old => ({
          ...old, card: draft.card, sourceUrl: draft.source_url ?? old.sourceUrl,
          profile: {
            ...old.profile, innovation_type: draft.innovation_type ?? old.profile.innovation_type,
            institution_type: draft.institution_type ?? old.profile.institution_type,
            institution: draft.institution ?? old.profile.institution, maturity: draft.maturity ?? old.profile.maturity,
          },
        }));
      }
      const notes = [];
      if (draft.category_status === "completed") notes.push("Sektory przypisano automatycznie na podstawie treści. Sprawdź je przed zapisem.");
      else if (draft.category_status === "uncertain") notes.push("Sektory są niepewne. Sprawdź, czy pasują do treści.");
      else notes.push("Nie udało się przypisać sektorów. Wybierz je ręcznie.");
      if (draft.card_status === "completed") notes.push(keepTitle ? "Opis karty uzupełniono z dokumentów." : "Nazwę i opis karty uzupełniono z dokumentów.");
      else notes.push("Nie udało się uzupełnić opisu. Możesz wpisać go ręcznie.");
      if (draft.skipped_files.length > 0) notes.push(`Pominięte pliki: ${draft.skipped_files.join(", ")}.`);
      setDraftNote(notes);
    } catch (cause) {
      if (draftRequest.current === request) setError(draftError(cause));
    } finally {
      if (draftRequest.current === request) setReading(false);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || reading) return;
    if (taken) { idInput.current?.focus(); return; }
    setBusy(true); setError(""); setSaved(null);
    const body = new FormData();
    body.append("meta", JSON.stringify(metaOf(form, null)));
    for (const file of files) body.append("files", file);
    try {
      const ingest = await api<IngestResult>(`api/v1/knowledge/innovations/${id}`, "PUT", body, uploadTimeoutMs);
      setSaved({ title: form.title.trim(), id, ingest });
      setForm(emptyForm); setId(""); setIdEdited(false); titleEdited.current = false;
      setFiles([]); setFileKey(key => key + 1); setDraftNote([]);
      await onSaved().catch(() => undefined);
    } catch (cause) {
      setError(saveError(cause, true));
    } finally { setBusy(false); }
  }

  return <>
    <p className={styles.modeLead}>Wybierz dokumenty nowej innowacji. System odczyta treść, przypisze sektory i uzupełni kartę. Przed zapisem możesz poprawić propozycję.</p>
    <p role="alert" className="form-error">{error}</p>
    <div role="status" aria-live="polite">
      {reading && <p className={styles.draftNote}>Odczytuję dokumenty i uzupełniam kartę…</p>}
      {draftNote.length > 0 && <div className={styles.draftNote}>{draftNote.map(note => <p key={note}>{note}</p>)}</div>}
      {saved && <div className="form-success">
        <SaveResult saved={saved} verb="Dodano" />
        <Button type="button" variant="link" className={styles.resultAction} onClick={() => onEdit(saved.id)}>Edytuj tę innowację</Button>
      </div>}
    </div>
    <div className="panel">
      <form onSubmit={submit} className={styles.uploadForm} aria-busy={busy || reading}>
        <label className="field-block">Pliki
          <Input key={fileKey} type="file" multiple required accept={fileTypes}
            onChange={e => readFiles(Array.from(e.target.files ?? []))} disabled={busy} aria-describedby="create-files-help" />
          <span id="create-files-help" className="field-help">PDF, DOCX lub ZIP. Nazwa, sektory i opis uzupełnią się na podstawie treści. Skany bez warstwy tekstowej zostaną pominięte.</span>
        </label>
        <label className="field-block">Nazwa innowacji
          <Input required maxLength={300} value={form.title} disabled={busy || reading}
            onChange={e => { const title = e.target.value; titleEdited.current = true; setForm(old => ({ ...old, title })); if (!idEdited) setId(slugify(title)); }} />
        </label>
        <label className="field-block">Identyfikator
          <Input ref={idInput} required maxLength={120} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={id} disabled={busy || reading}
            aria-invalid={taken ? true : undefined} aria-describedby={taken ? "create-id-taken create-id-help" : "create-id-help"}
            onChange={e => { setId(e.target.value); setIdEdited(true); }} />
          <span id="create-id-help" className="field-help">Małe litery, cyfry i myślniki, np. „czujnik-powietrza”. Tworzy się automatycznie z nazwy.</span>
        </label>
        {taken && <div id="create-id-taken" className={styles.replaceNote}>
          <p>Innowacja „{taken.title}” ma już ten identyfikator. Zmień nazwę lub identyfikator albo popraw istniejącą innowację.</p>
          <Button type="button" variant="link" className={styles.resultAction} onClick={() => onEdit(taken.id)}>Edytuj „{taken.title}”</Button>
        </div>}
        <CardFields form={form} onChange={setForm} taxonomy={taxonomy} disabled={busy || reading} reading={reading} />
        <Button type="submit" size="lg" disabled={busy || reading || !form.primary}>
          {busy ? "Przetwarzam dokumenty… To może potrwać kilka minut." : reading ? "Odczytuję dokumenty…" : "Dodaj innowację"}
        </Button>
      </form>
    </div>
  </>;
}

function EditInnovation({ innovation, taxonomy, busy, setBusy, onSaved }: {
  innovation: Innovation; taxonomy: Taxonomy;
  busy: boolean; setBusy: (busy: boolean) => void; onSaved: () => Promise<unknown>;
}) {
  const [form, setForm] = useState<CardForm>(() => formOf(innovation));
  const [files, setFiles] = useState<File[]>([]);
  const [fileKey, setFileKey] = useState(0);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Saved | null>(null);
  const replacing = files.length > 0;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setSaved(null);
    const meta = metaOf(form, innovation.video_url);
    const path = `api/v1/knowledge/innovations/${innovation.id}`;
    try {
      let ingest: IngestResult | null = null;
      if (replacing) {
        const body = new FormData();
        body.append("meta", JSON.stringify(meta));
        for (const file of files) body.append("files", file);
        ingest = await api<IngestResult>(path, "PUT", body, uploadTimeoutMs);
        setFiles([]); setFileKey(key => key + 1);
      } else {
        await api<Innovation>(path, "PATCH", meta, uploadTimeoutMs);
      }
      setSaved({ title: meta.title, id: innovation.id, ingest });
      await onSaved().catch(() => undefined);
    } catch (cause) {
      setError(saveError(cause, replacing));
    } finally { setBusy(false); }
  }

  const documents = innovation.documents.filter(d => documentUrl.test(d.download_url));

  return <>
    <p role="alert" className="form-error">{error}</p>
    <div role="status" aria-live="polite">
      {saved && <div className="form-success"><SaveResult saved={saved} verb="Zapisano" /></div>}
    </div>
    <div className="panel">
      <form onSubmit={submit} className={styles.uploadForm} aria-busy={busy}>
        <label className="field-block">Nazwa innowacji
          <Input required maxLength={300} value={form.title} disabled={busy} aria-describedby="edit-id-help"
            onChange={e => { const title = e.target.value; setForm(old => ({ ...old, title })); }} />
          <span id="edit-id-help" className="field-help">Identyfikator: {innovation.id}. Nie zmienia się przy edycji.</span>
        </label>
        <CardFields form={form} onChange={setForm} taxonomy={taxonomy} disabled={busy} />
        <fieldset className={styles.documents} disabled={busy}>
          <legend>Dokumenty</legend>
          {documents.length > 0
            ? <ul className="document-list">
              {documents.map(d => <li key={d.id}>
                <a href={`/api/backend${d.download_url}`} target="_blank" rel="noopener noreferrer"><FileText aria-hidden="true" size={16} />{d.filename}<span className="sr-only"> (otwiera się w nowej karcie)</span></a>
              </li>)}
            </ul>
            : <p className={styles.empty}>Ta innowacja nie ma jeszcze dokumentów.</p>}
          <label className="field-block">Nowe dokumenty (opcjonalnie)
            <Input key={fileKey} type="file" multiple accept={fileTypes}
              onChange={e => { setFiles(Array.from(e.target.files ?? [])); setSaved(null); }} aria-describedby="edit-files-help" />
            <span id="edit-files-help" className="field-help">PDF, DOCX lub ZIP. Bez nowych plików zapiszesz tylko zmiany w karcie, a obecne dokumenty zostaną.</span>
          </label>
          {replacing && <p className={styles.replaceNote}>Zapis zastąpi wszystkie obecne dokumenty ({innovation.files.length > 0 ? innovation.files.join(", ") : "brak"}) wybranymi plikami i ponownie je zindeksuje.</p>}
        </fieldset>
        <Button type="submit" size="lg" disabled={busy || !form.primary}>
          {busy ? (replacing ? "Przetwarzam dokumenty… To może potrwać kilka minut." : "Zapisuję zmiany…") : replacing ? "Zapisz i zastąp dokumenty" : "Zapisz zmiany"}
        </Button>
      </form>
    </div>
  </>;
}

export function DocumentsView() {
  const [taxonomy, setTaxonomy] = useState<Taxonomy>({ sectors: {}, innovation_types: {}, institution_types: {}, maturity: {} });
  const [innovations, setInnovations] = useState<Innovation[]>([]);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<Mode>("create");
  const [selected, setSelected] = useState("");
  const [editBusy, setEditBusy] = useState(false);

  const loadInnovations = () => api<Innovation[]>("api/v1/knowledge/innovations").then(setInnovations);

  useEffect(() => {
    api<Taxonomy>("api/v1/knowledge/taxonomy").then(setTaxonomy, () => setLoadError("Nie udało się wczytać sektorów i słowników."));
    api<Innovation[]>("api/v1/knowledge/innovations").then(setInnovations, () => setLoadError("Nie udało się wczytać listy innowacji. Możesz dodać nową."));
  }, []);

  function edit(id: string) {
    if (!editBusy) setSelected(id);
    setMode("edit");
  }

  const editing = innovations.find(item => item.id === selected);

  return <section aria-labelledby="documents-title">
    <div className="page-intro">
      <h1 id="documents-title">Innowacje w bazie wiedzy</h1>
      <p>Dodaj nową innowację z dokumentów albo popraw kartę i dokumenty istniejącej. Teksty zostaną zindeksowane, aby asystent mógł z nich korzystać.</p>
    </div>
    <p role="alert" className="form-error">{loadError}</p>
    <Tabs.Root value={mode} onValueChange={next => setMode(next as Mode)}>
      <Tabs.List className={styles.modeTabs} aria-label="Praca z innowacjami">
        <Tabs.Tab value="create" className={styles.modeTab}>Nowa innowacja</Tabs.Tab>
        <Tabs.Tab value="edit" className={styles.modeTab}>Edytuj istniejącą</Tabs.Tab>
      </Tabs.List>
      {/* Both panels stay mounted so a running upload and unsaved input survive a tab switch. */}
      <Tabs.Panel value="create" keepMounted tabIndex={-1} className={styles.modePanel}>
        <CreateInnovation taxonomy={taxonomy} innovations={innovations} onSaved={loadInnovations} onEdit={edit} />
      </Tabs.Panel>
      <Tabs.Panel value="edit" keepMounted tabIndex={-1} className={styles.modePanel}>
        <p className={styles.modeLead}>Wybierz innowację, aby poprawić jej kartę lub zastąpić dokumenty.</p>
        <label className={`field-block ${styles.picker}`}>Innowacja
          <select className="select" value={selected} onChange={e => setSelected(e.target.value)} disabled={editBusy}>
            <option value="" disabled>{innovations.length > 0 ? "Wybierz innowację" : "Brak innowacji w bazie wiedzy"}</option>
            {innovations.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </label>
        {editing && <EditInnovation key={editing.id} innovation={editing} taxonomy={taxonomy}
          busy={editBusy} setBusy={setEditBusy} onSaved={loadInnovations} />}
      </Tabs.Panel>
    </Tabs.Root>
  </section>;
}
