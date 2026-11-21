"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/features/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus } from "@/components/ui/icons";
import { createMatter, formatMatterDate, listMatters, matterStatusLabels, matterTypeLabels, type MatterPage, type MatterType } from "./api";
import styles from "./matters.module.css";

const pageSize = 20;

export function SignInPrompt() {
  return <section className="page-intro"><h1>Moje sprawy</h1><p>Aby zobaczyć swoje sprawy, najpierw wybierz rolę.</p><Button nativeButton={false} render={<Link href="/rozmowa" />}>Wybierz rolę</Button></section>;
}

export function MatterStatusLabel({ status }: { status: keyof typeof matterStatusLabels }) {
  return <span className={`${styles.status} ${styles[`status-${status}`]}`}>Status: {matterStatusLabels[status]}</span>;
}

/** "Moje sprawy": the user's matters, newest first, with a form for a new one. */
export function MatterList() {
  const router = useRouter();
  const [page, setPage] = useState<MatterPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [signedOut, setSignedOut] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [type, setType] = useState<MatterType>("idea_card");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    listMatters(offset, pageSize).then(data => { if (active) setPage(data); }).catch(cause => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 401) setSignedOut(true);
      else { setPage({ total: 0, items: [] }); setError("Nie udało się wczytać spraw. Odśwież stronę."); }
    });
    return () => { active = false; };
  }, [offset]);

  useEffect(() => { if (creating) titleRef.current?.focus(); }, [creating]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const matter = await createMatter(title.trim(), type);
      router.push(`/matters/${matter.id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) setSignedOut(true);
      else setError(cause instanceof ApiError && cause.status === 422 ? "Podaj tytuł (najwyżej 200 znaków)." : "Nie udało się utworzyć sprawy. Spróbuj ponownie.");
      setBusy(false);
    }
  }

  if (signedOut) return <SignInPrompt />;
  if (!page) return <p role="status" className="page-status">Wczytuję sprawy…</p>;

  return <section aria-labelledby="matters-title">
    <div className={`page-intro ${styles.intro}`}>
      <div>
        <h1 id="matters-title">Moje sprawy</h1>
        <p>Twoje karty innowacji, zgłoszenia, plany wdrożenia i notatki. Możesz je edytować ręcznie albo omówić w rozmowie z asystentem.</p>
      </div>
      {!creating && <Button onClick={() => setCreating(true)}><Plus aria-hidden="true" />Nowa sprawa</Button>}
    </div>
    <p role="alert" className="form-error">{error}</p>
    {creating && <form className={`panel ${styles.createForm}`} onSubmit={create} aria-labelledby="new-matter-title">
      <h2 id="new-matter-title">Nowa sprawa</h2>
      <label className="field-block">Tytuł<Input ref={titleRef} required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} disabled={busy} /></label>
      <label className="field-block">Rodzaj<select className="select" value={type} onChange={e => setType(e.target.value as MatterType)} disabled={busy}>
        {Object.entries(matterTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <div className={styles.actions}>
        <Button type="submit" disabled={busy || !title.trim()}>{busy ? "Tworzę…" : "Utwórz sprawę"}</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setCreating(false); setTitle(""); }}>Anuluj</Button>
      </div>
    </form>}
    <p role="status" className="result-count">Liczba spraw: {page.total}</p>
    {!page.items.length ? <div className="panel empty-state">
      <p>Nie masz jeszcze żadnych spraw. Utwórz nową albo poproś asystenta w rozmowie, aby zapisał opis Twojej innowacji.</p>
      {!creating && <Button onClick={() => setCreating(true)}><Plus aria-hidden="true" />Nowa sprawa</Button>}
    </div> : <ul className={styles.list} aria-label="Lista spraw">{page.items.map(matter => <li key={matter.id} className={`panel ${styles.item}`}>
      <Link className={styles.itemTitle} href={`/matters/${matter.id}`}>{matter.title}</Link>
      <p className={styles.meta}>
        <span>{matterTypeLabels[matter.type]}</span>
        <MatterStatusLabel status={matter.status} />
        <span>Zmieniono: {formatMatterDate(matter.updated_at)}</span>
      </p>
    </li>)}</ul>}
    {page.total > pageSize && <div className="pager">
      <Button variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - pageSize)}>Poprzednie</Button>
      <Button variant="outline" disabled={offset + pageSize >= page.total} onClick={() => setOffset(offset + pageSize)}>Następne</Button>
    </div>}
  </section>;
}
