"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/features/workspace";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/ui/markdown";
import { ArrowLeft } from "@/components/ui/icons";
import { deleteMatter, downloadMatterPdf, formatMatterDate, getMatter, matterStatusLabels, matterThread, matterTypeLabels, updateMatter, type Matter, type MatterStatus } from "./api";
import { MatterStatusLabel, SignInPrompt } from "./list";
import styles from "./matters.module.css";

type Draft = { title: string; status: MatterStatus; content: string; revision: number };

/** One matter: rendered Markdown, a compare-and-swap editor, delete and "ask in chat". */
export function MatterDetail({ id }: { id: number }) {
  const router = useRouter();
  const [matter, setMatter] = useState<Matter | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "signed-out" | "failed">("loading");
  const [draft, setDraft] = useState<Draft | null>(null);
  // Newer version saved elsewhere while the user was editing; their text stays in the editor.
  const [conflict, setConflict] = useState<Matter | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let active = true;
    // An invalid id is rejected with 404 by the proxy allowlist or the backend.
    getMatter(id).then(data => { if (active) { setMatter(data); setState("ready"); } }).catch(cause => {
      if (!active) return;
      setState(cause instanceof ApiError && cause.status === 401 ? "signed-out" : cause instanceof ApiError && cause.status === 404 ? "missing" : "failed");
    });
    return () => { active = false; };
  }, [id]);

  useEffect(() => { if (matter) document.title = `${matter.title} - Moje sprawy - Radar innowacji`; }, [matter]);

  function fail(cause: unknown, fallback: string) {
    if (cause instanceof ApiError && cause.status === 401) setState("signed-out");
    else if (cause instanceof ApiError && cause.status === 404) setState("missing");
    else setError(cause instanceof ApiError && cause.status === 422 ? "Sprawdź tytuł (1–200 znaków) i treść (najwyżej 20 000 znaków)." : fallback);
  }

  function edit() {
    if (!matter) return;
    setDraft({ title: matter.title, status: matter.status, content: matter.content_markdown, revision: matter.revision });
    setConflict(null); setError(""); setMessage("");
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!matter || !draft) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await updateMatter(matter.id, { expected_revision: draft.revision, title: draft.title.trim(), status: draft.status, content_markdown: draft.content });
      setMatter(saved); setDraft(null); setConflict(null); setMessage("Zapisano zmiany.");
      heading.current?.focus();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        try {
          const current = await getMatter(matter.id);
          setMatter(current); setConflict(current);
          setError("Sprawa została zmieniona w międzyczasie. Twoje zmiany nie zostały zapisane. Porównaj je z aktualną wersją poniżej.");
        } catch (reload) { fail(reload, "Nie udało się wczytać aktualnej wersji. Odśwież stronę."); }
      } else fail(cause, "Nie udało się zapisać zmian. Spróbuj ponownie.");
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!matter) return;
    setBusy(true); setError("");
    try {
      await deleteMatter(matter.id);
      router.push("/matters");
    } catch (cause) { setConfirmDelete(false); fail(cause, "Nie udało się usunąć sprawy. Spróbuj ponownie."); setBusy(false); }
  }

  async function askInChat() {
    if (!matter) return;
    setBusy(true); setError("");
    try {
      const { conversation_id } = await matterThread(matter.id);
      router.push(`/rozmowa?conversation=${conversation_id}`);
    } catch (cause) { fail(cause, "Nie udało się otworzyć rozmowy. Spróbuj ponownie."); setBusy(false); }
  }

  async function downloadPdf() {
    if (!matter) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await downloadMatterPdf(matter.id, matter.title);
      setMessage("Pobrano PDF sprawy.");
    } catch (cause) { fail(cause, "Nie udało się pobrać PDF. Spróbuj ponownie."); }
    finally { setBusy(false); }
  }

  if (state === "loading") return <p role="status" className="page-status">Wczytuję sprawę…</p>;
  if (state === "signed-out") return <SignInPrompt />;
  if (state === "missing") return <section className="page-intro"><h1>Nie znaleziono sprawy</h1><p>Ta sprawa nie istnieje albo została usunięta.</p><Button nativeButton={false} render={<Link href="/matters" />}>Wróć do Moich spraw</Button></section>;
  if (state === "failed" || !matter) return <div className="page-status"><p role="alert">Nie udało się wczytać sprawy.</p><Button onClick={() => window.location.reload()}>Spróbuj ponownie</Button></div>;

  return <article aria-labelledby="matter-title">
    <Link className={styles.back} href="/matters"><ArrowLeft aria-hidden="true" size={16} />Moje sprawy</Link>
    <div className={styles.header}>
      <h1 id="matter-title" ref={heading} tabIndex={-1}>{matter.title}</h1>
      <p className={styles.meta}>
        <span>{matterTypeLabels[matter.type]}</span>
        <MatterStatusLabel status={matter.status} />
        <span>Zmieniono: {formatMatterDate(matter.updated_at)}</span>
      </p>
    </div>
    <p role="alert" className="form-error">{error}</p>
    <p role="status" className="form-success">{message}</p>
    {!draft ? <>
      <div className={styles.actions}>
        <Button onClick={edit} disabled={busy}>Edytuj</Button>
        <Button variant="outline" onClick={() => void downloadPdf()} disabled={busy}>Pobierz PDF</Button>
        <Button variant="outline" onClick={() => void askInChat()} disabled={busy}>Zapytaj w czacie o tę sprawę</Button>
        <Button variant="destructive" onClick={() => setConfirmDelete(true)} disabled={busy}>Usuń sprawę</Button>
      </div>
      <section className={`panel ${styles.content}`} aria-label="Treść sprawy">
        {matter.content_markdown.trim() ? <Markdown text={matter.content_markdown} /> : <p className="field-help">Ta sprawa nie ma jeszcze treści. Wybierz „Edytuj”, aby ją uzupełnić.</p>}
      </section>
    </> : <form className={`panel ${styles.editor}`} onSubmit={save} aria-label="Edycja sprawy">
      <label className="field-block">Tytuł<Input required maxLength={200} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} disabled={busy} /></label>
      <label className="field-block">Status<select className="select" value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value as MatterStatus })} disabled={busy}>
        {Object.entries(matterStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="field-block">Treść (Markdown)
        <Textarea className={`field-textarea ${styles.markdownInput}`} maxLength={20000} value={draft.content} onChange={e => setDraft({ ...draft, content: e.target.value })} disabled={busy} aria-describedby="matter-content-help" />
        <span id="matter-content-help" className="field-help">Sekcje zaczynaj od „## ”. Najwyżej 20 000 znaków.</span>
      </label>
      {conflict && <section className={styles.conflict} aria-labelledby="conflict-title">
        <h2 id="conflict-title">Aktualna wersja sprawy</h2>
        <p className="field-help">Zapisana {formatMatterDate(conflict.updated_at)}. Twój tekst powyżej pozostał bez zmian.</p>
        <div className={styles.conflictContent}><Markdown text={conflict.content_markdown} /></div>
        <div className={styles.actions}>
          <Button type="button" onClick={() => { setDraft({ ...draft, revision: conflict.revision }); setConflict(null); setError(""); setMessage("Twoje zmiany zastąpią aktualną wersję po zapisaniu."); }} disabled={busy}>Zastosuj moje zmiany do aktualnej wersji</Button>
          <Button type="button" variant="outline" onClick={() => { setDraft({ title: conflict.title, status: conflict.status, content: conflict.content_markdown, revision: conflict.revision }); setConflict(null); setError(""); setMessage("Wczytano aktualną wersję do edycji."); }} disabled={busy}>Odrzuć moje zmiany</Button>
        </div>
      </section>}
      <div className={styles.actions}>
        <Button type="submit" disabled={busy || Boolean(conflict) || !draft.title.trim()}>{busy ? "Zapisuję…" : "Zapisz"}</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setDraft(null); setConflict(null); setError(""); }}>Anuluj</Button>
      </div>
    </form>}
    <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Usunąć sprawę?">
      <p>Sprawa „{matter.title}” zostanie trwale usunięta. Tej operacji nie można cofnąć.</p>
      <div className={styles.actions}>
        <Button variant="destructive" disabled={busy} onClick={() => void remove()}>{busy ? "Usuwam…" : "Usuń sprawę"}</Button>
        <Button variant="outline" disabled={busy} onClick={() => setConfirmDelete(false)}>Anuluj</Button>
      </div>
    </Dialog>
  </article>;
}
