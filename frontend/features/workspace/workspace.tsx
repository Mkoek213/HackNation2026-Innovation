"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { flushSync } from "react-dom";
import { Menu, Mic, Plus, Send, Trash2 } from "@/components/ui/icons";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/ui/markdown";
import { api, ApiError, Artifact, CreatorState, Detail, download, Innovation, MatterLink, notifySession, Operation, safeLink, session, Thread, User } from "./api";
import { Sources } from "./sources";
import { Handoff } from "./handoff";
import { useDictation } from "./dictation";

type Pending = { thread: number; key: string };
const base = "workspace/conversations";
const waitMessage = "Poczekaj na odpowiedź. Wysyłanie i edycja wiadomości są chwilowo wyłączone.";
const artifactTypes: Record<Artifact["type"], string> = { idea_card: "Karta innowacji", application_draft: "Zgłoszenie do Radaru", adaptation_plan: "Plan wdrożenia" };
const matterTypes: Record<MatterLink["type"], string> = { ...artifactTypes, note: "Notatka" };
// Fixed messages of the opt-in innovation submission creator; the agent switches the mode with its idea_creator tool.
const creatorMessages = {
  finish: "Zakończ kreator i zapisz zgłoszenie w Moich sprawach.",
  cancel: "Przerwij kreator bez zapisywania zgłoszenia.",
};
// Ready-made openings of a new conversation; the person fills in each "…" before sending.
const starters = [
  { title: "Sprawdź dowody wdrożenia", text: "Sprawdź, gdzie rozwiązanie … zostało użyte. Podaj źródło i opisz warunki wdrożenia." },
  { title: "Sprawdź, czy to już istnieje", text: "Mamy pomysł na … Czy w bazie są podobne rozwiązania?" },
  { title: "Znajdź rozwiązanie do wdrożenia", text: "Reprezentuję … (gminę, szkołę, firmę). Szukamy rozwiązania problemu … Co jest w bazie?" },
  { title: "Zaplanuj wdrożenie", text: "Chcemy wdrożyć innowację … w … Od czego zacząć i czego będziemy potrzebować?" },
  { title: "Ścieżka rozwoju", text: "Nasza innowacja … jest na etapie … Jakie są możliwe ścieżki rozwoju, transferu lub komercjalizacji?" },
  { title: "Szukam partnera", text: "Rozwijamy … Szukamy partnera do pilotażu lub finansowania. Kto mógłby być zainteresowany?" },
];
// Fixed demo accounts. The visitor never types credentials; missing accounts are registered on entry.
const demoAccounts = {
  user: { username: "uzytkownik", email: "uzytkownik@example.com", password: "demo-haslo-2026", role: "user" },
  admin: { username: "administrator", email: "administrator@example.com", password: "demo-haslo-2026", role: "admin" },
} as const;

export function Workspace() {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [view, setView] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState("");
  const [authError, setAuthError] = useState("");
  const [entering, setEntering] = useState<keyof typeof demoAccounts | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const deletingRef = useRef<number | null>(null);
  const [source, setSource] = useState<Innovation | null>(null);
  const [handoff, setHandoff] = useState(false);
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const selected = useRef<number | null>(null);
  const owner = useRef<number | null>(null);
  const generation = useRef(0);
  const sending = useRef(false);
  const pendingRef = useRef<Pending | null>(null);
  // Example question from the home page (?pytanie=…), sent as the first message of a new conversation.
  const question = useRef<string | null>(null);
  const cache = useRef(new Map<number, Detail>());
  const positions = useRef(new Map<number, number>());
  const scroll = useRef<HTMLElement>(null);
  const renderedTurn = useRef<{ thread: number; content: string } | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const writeDraft = useCallback((value: string) => {
    const id = selected.current;
    if (id == null) return;
    setDrafts(old => ({ ...old, [id]: value }));
  }, []);
  const { listening, notice, toggle, edited, cancel } = useDictation(input, writeDraft);

  const updatePending = useCallback((value: Pending | null) => {
    pendingRef.current = value; sending.current = Boolean(value); setPending(value);
  }, []);

  const handleError = useCallback((cause: unknown) => {
    if (cause instanceof ApiError && cause.status === 401) {
      generation.current += 1;
      setUser(null); setThreads([]); setView(null); setSource(null); setDrawer(false); setHandoff(false);
      cache.current.clear(); updatePending(null); notifySession();
      setAuthError("Sesja wygasła. Wybierz rolę ponownie. Szkice pozostają w tej karcie.");
    } else setError(cause instanceof ApiError && cause.status === 409
      ? "Wiadomość jest już przetwarzana lub można ponowić tylko ostatnią wiadomość. Odśwież rozmowę."
      : "Nie udało się wykonać działania. Spróbuj ponownie.");
  }, [updatePending]);

  const read = useCallback(async (id: number) => {
    const epoch = generation.current;
    const data = await api<Detail>(`${base}/${id}`);
    if (epoch !== generation.current) return null;
    // Keep the immediate local message visible until the backend has accepted it.
    const local = cache.current.get(id)?.operations.filter(o => o.id < 0 && !data.operations.some(saved => saved.key === o.key)) || [];
    data.operations.push(...local);
    cache.current.set(id, data);
    if (selected.current === id) setView(data);
    const last = data.operations.at(-1);
    if (last?.status === "failed") setDrafts(old => old[id] === undefined ? { ...old, [id]: last.content } : old);
    return data;
  }, []);

  const refresh = useCallback(async () => {
    const epoch = generation.current;
    const all: Thread[] = [];
    for (let offset = 0; ; offset += 100) {
      const page = await api<Thread[]>(`${base}?limit=100&offset=${offset}`);
      all.push(...page);
      if (page.length < 100) break;
    }
    if (epoch !== generation.current) return [];
    setThreads(all);
    if (!pendingRef.current) {
      const processing = all.find(t => t.pending);
      if (processing) {
        const data = await read(processing.id);
        const op = data?.operations.find(o => o.status === "processing");
        if (op) updatePending({ thread: processing.id, key: op.key });
      }
    }
    return all;
  }, [read, updatePending]);

  const open = useCallback(async (id: number) => {
    cancel();
    if (scroll.current && selected.current) positions.current.set(selected.current, scroll.current.scrollTop);
    selected.current = id;
    window.history.replaceState(null, "", `?conversation=${id}`);
    setDrawer(false); setHandoff(false); setArtifactId(null); setSource(null); setError(""); setLoading(true); setView(cache.current.get(id) || null);
    try { await read(id); } catch (cause) { handleError(cause); }
    finally { if (selected.current === id) setLoading(false); }
  }, [read, handleError, cancel]);

  function openSource(threadId: number, innovation: Innovation) {
    setSource(innovation);
    // Only feeds the admin ranking; a failure must not affect reading the sources.
    void api(`${base}/${threadId}/innovations/${encodeURIComponent(innovation.id)}/open`, "POST").catch(() => undefined);
  }

  const newThread = useCallback(async () => {
    const epoch = generation.current;
    setLoading(true);
    try {
      const thread = await api<Thread>(base, "POST");
      if (epoch !== generation.current) return;
      await refresh(); await open(thread.id);
    } catch (cause) { handleError(cause); }
    finally { setLoading(false); }
  }, [refresh, open, handleError]);

  async function deleteThread(id: number) {
    if (deletingRef.current !== null || loading || pendingRef.current?.thread === id) return;
    const epoch = generation.current;
    deletingRef.current = id; setDeleting(id); setLoading(true); setError("");
    try {
      await api(`${base}/${id}`, "DELETE");
      if (epoch !== generation.current) return;
      const remaining = threads.filter(thread => thread.id !== id);
      setThreads(remaining);
      cache.current.delete(id); positions.current.delete(id);
      setDrafts(old => {
        const next = { ...old };
        delete next[id];
        return next;
      });
      if (selected.current === id) {
        cancel(); selected.current = null; setView(null);
        setSource(null); setHandoff(false); setArtifactId(null);
        window.history.replaceState(null, "", "/rozmowa");
        if (remaining.length) await open(remaining[0].id);
        else await newThread();
      }
      input.current?.focus();
    } catch (cause) {
      if (epoch === generation.current) handleError(cause);
    } finally {
      deletingRef.current = null; setDeleting(null); setLoading(false);
    }
  }

  const restore = useCallback(async (account: User) => {
    if (owner.current !== null && owner.current !== account.id) {
      selected.current = null; cache.current.clear(); positions.current.clear(); setDrafts({});
      window.history.replaceState(null, "", "/rozmowa");
    }
    owner.current = account.id;
    setUser(account); setAuthError("");
    const list = await refresh();
    const params = new URLSearchParams(window.location.search);
    const asked = params.get("pytanie")?.trim().slice(0, 4000);
    if (asked || params.get("nowa") === "1") {
      question.current = asked || null;
      await newThread();
      return;
    }
    const fromUrl = Number(params.get("conversation"));
    const target = list.find(t => t.id === (selected.current || fromUrl)) || list[0];
    if (target) await open(target.id); else await newThread();
  }, [refresh, open, newThread]);

  useEffect(() => {
    let active = true;
    session().then(account => { if (active) return restore(account); }).catch(cause => {
      if (!active) return;
      if (owner.current !== null) handleError(cause);
      else if (!(cause instanceof ApiError) || cause.status !== 401) setAuthError("Nie można połączyć się z serwerem. Spróbuj ponownie.");
    }).finally(() => { if (active) setInitializing(false); });
    return () => { active = false; };
  }, [restore, handleError]);

  useEffect(() => {
    if (!pending || !user) return;
    let active = true;
    let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const data = await read(pending.thread);
        if (!active || !data) return;
        const operation = data.operations.find(o => o.key === pending.key);
        if (operation && operation.id >= 0 && operation.status !== "processing") {
          if (operation.status === "completed") setDrafts(old => ({ ...old, [pending.thread]: "" }));
          else setDrafts(old => ({ ...old, [pending.thread]: operation.content }));
          updatePending(null); await refresh();
        }
      } catch (cause) {
        if (active && cause instanceof ApiError && cause.status === 404) { updatePending(null); await refresh().catch(handleError); }
        else if (active) handleError(cause);
      } finally { polling = false; }
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pending, user, read, refresh, handleError, updatePending]);

  useEffect(() => {
    if (!user) return;
    const timer = window.setInterval(() => { session().catch(handleError); }, 60000);
    const reconnect = () => { refresh().catch(handleError); if (selected.current) read(selected.current).catch(handleError); };
    window.addEventListener("online", reconnect);
    return () => { window.clearInterval(timer); window.removeEventListener("online", reconnect); };
  }, [user, read, refresh, handleError]);

  useEffect(() => {
    if (!view || !scroll.current || loading) return;
    const latest = view.operations.at(-1);
    // Polling returns fresh objects even when the visible turn has not changed.
    const content = JSON.stringify([latest?.key, latest?.status, latest?.result?.answer, pending?.thread === view.id]);
    const previous = renderedTurn.current;
    const turnChanged = previous?.thread === view.id && previous.content !== content;
    const position = turnChanged ? scroll.current.scrollHeight : positions.current.get(view.id) ?? scroll.current.scrollHeight;
    scroll.current.scrollTop = position;
    positions.current.set(view.id, scroll.current.scrollTop);
    renderedTurn.current = { thread: view.id, content };
  }, [view, pending, loading]);

  async function enterAs(role: keyof typeof demoAccounts) {
    if (entering) return;
    const account = demoAccounts[role];
    setEntering(role); setAuthError("");
    let restoring = false;
    try {
      try {
        await api("auth/register", "POST", account);
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 409) throw cause;
      }
      await api("auth/login", "POST", { username: account.username, password: account.password });
      restoring = true; notifySession();
      await restore(await session());
    } catch (cause) {
      if (restoring) { handleError(cause); return; }
      setAuthError(cause instanceof ApiError && cause.status === 401 ? "Konto demonstracyjne już istnieje i nie można na nie wejść."
        : cause instanceof ApiError && cause.status === 403 ? "Żądanie zostało odrzucone przez serwer. Odśwież stronę i spróbuj ponownie."
        : cause instanceof ApiError && cause.status === 429 ? "Zbyt wiele prób. Spróbuj za chwilę."
        : cause instanceof ApiError && cause.status === 503 ? "Nie można połączyć się z serwerem. Spróbuj ponownie."
        : "Nie udało się wejść. Spróbuj ponownie.");
    } finally { setEntering(null); }
  }

  async function send(retry?: Operation, preset?: string) {
    cancel();
    if (!view || sending.current || loading) return;
    const content = retry?.content || preset || drafts[view.id]?.trim();
    if (!content) return;
    const id = view.id;
    const epoch = generation.current;
    const previous = view.operations.at(-1);
    if (!retry && previous?.status === "failed" && previous.content === content) retry = previous;
    const key = retry?.key || crypto.randomUUID();
    updatePending({ thread: id, key }); setError("");
    // A preset message (creator buttons) keeps whatever the user is typing.
    if (!preset) setDrafts(old => ({ ...old, [id]: "" }));
    const optimistic: Operation = { id: retry?.id ?? -1, key, content, status: "processing", result: null };
    const updated = { ...view, operations: retry ? view.operations.map(o => o.key === key ? optimistic : o) : [...view.operations, optimistic] };
    cache.current.set(id, updated); setView(updated);
    positions.current.delete(id);
    try {
      const operation = await api<Operation>(`${base}/${id}/messages`, "POST", { key, content });
      if (epoch !== generation.current) return;
      const data = cache.current.get(id)!;
      const finished = { ...data, operations: data.operations.map(o => o.key === key ? operation : o) };
      cache.current.set(id, finished); if (selected.current === id) setView(finished);
      if (operation.status !== "processing") {
        setDrafts(old => ({ ...old, [id]: operation.status === "completed" ? (old[id]?.trim() === content ? "" : old[id] ?? "") : content }));
        if (pendingRef.current?.key === key) updatePending(null); await refresh();
      }
    } catch (cause) {
      if (epoch !== generation.current) return;
      if (cause instanceof ApiError && cause.status === 401) { handleError(cause); return; }
      // A lost response may conceal success. Recover persisted status before enabling retry.
      try {
        const recovered = await read(id);
        const saved = recovered?.operations.find(o => o.key === key && o.id >= 0);
        if (saved) {
          if (saved.status !== "processing") {
            setDrafts(old => ({ ...old, [id]: saved.status === "completed" ? (old[id]?.trim() === content ? "" : old[id] ?? "") : content })); if (pendingRef.current?.key === key) updatePending(null);
          }
          await refresh(); return;
        }
      } catch (recoveryError) {
        if (recoveryError instanceof ApiError && recoveryError.status === 401) { handleError(recoveryError); return; }
      }
      const data = cache.current.get(id);
      if (data) {
        const failed = { ...data, operations: data.operations.map(o => o.key === key ? { ...o, status: "failed" as const } : o) };
        cache.current.set(id, failed); if (selected.current === id) setView(failed);
      }
      setDrafts(old => ({ ...old, [id]: content })); if (pendingRef.current?.key === key) updatePending(null); handleError(cause);
    } finally { if (selected.current === id) input.current?.focus(); }
  }

  useEffect(() => {
    const asked = question.current;
    if (!asked || !view || view.operations.length > 0 || pending || loading) return;
    question.current = null;
    void send(undefined, asked);
    // send is recreated on every render; the ref guarantees a single dispatch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, pending, loading]);

  /** Puts a ready-made opening into the composer and selects its first gap, so typing or dictation fills it. */
  function pickStarter(text: string) {
    if (!view) return;
    // Text already in the composer stays; the opening goes below it.
    const kept = (drafts[view.id] ?? "").replace(/\s+$/, "");
    const at = kept ? kept.length + 2 : 0;
    const next = (kept ? `${kept}\n\n${text}` : text).slice(0, 4000);
    edited(next);
    flushSync(() => setDrafts(old => ({ ...old, [view.id]: next })));
    const field = input.current;
    if (!field) return;
    field.focus();
    const gap = next.indexOf("…", at);
    if (gap >= 0) field.setSelectionRange(gap, gap + 1);
    else field.setSelectionRange(next.length, next.length);
  }

  const history = <div className="history-content">
    <Button variant="outline" disabled={loading} onClick={() => void newThread()}><Plus aria-hidden="true" />Nowa rozmowa</Button>
    <nav aria-label="Historia rozmów">{threads.length === 0 && <p className="history-empty">Brak zapisanych rozmów.</p>}{threads.map(thread => {
      const active = view?.id === thread.id;
      const title = thread.title || "Nowa rozmowa";
      const busy = thread.pending || pending?.thread === thread.id;
      return <div key={thread.id} className="history-item" data-active={active || undefined}>
        <button
          type="button"
          className="history-row"
          aria-current={active ? "true" : undefined}
          disabled={deleting !== null}
          onClick={() => void open(thread.id)}
        >
          {title}{busy && <span className="sr-only">, przetwarzanie</span>}
        </button>
        <button
          type="button"
          className="history-delete"
          aria-label={deleting === thread.id ? `Usuwam rozmowę: ${title}` : `Usuń rozmowę: ${title}`}
          title={busy ? "Poczekaj na zakończenie odpowiedzi" : "Usuń rozmowę"}
          disabled={loading || deleting !== null || busy}
          onClick={() => void deleteThread(thread.id)}
        ><Trash2 size={18} aria-hidden="true" /></button>
      </div>;
    })}</nav>
  </div>;

  if (initializing) return <main id="main" className="auth-screen"><p role="status">Sprawdzam sesję…</p></main>;
  if (!user) return <main id="main" tabIndex={-1} className="auth-screen"><Card className="auth-card"><div className="auth-form">
    <h1>Wejdź do Radaru innowacji</h1>
    <p className="auth-lead">Wersja demonstracyjna. Wybierz rolę, aby rozpocząć.</p>
    <div className="auth-choices">
      <Button type="button" disabled={entering !== null} onClick={() => void enterAs("user")}>{entering === "user" ? "Proszę czekać…" : "Użytkownik"}</Button>
      <Button type="button" disabled={entering !== null} onClick={() => void enterAs("admin")}>{entering === "admin" ? "Proszę czekać…" : "Administrator"}</Button>
    </div>
    <p role="status" className="sr-only">{entering ? "Proszę czekać…" : ""}</p>
    <p role="alert">{authError}</p>
  </div></Card></main>;

  const last = view?.operations.at(-1);
  // The creator mode is part of each completed answer; the newest one is current (and survives a reload).
  const creator = view?.operations.filter(o => o.status === "completed" && o.result?.creator).at(-1)?.result?.creator;
  // A document can be revised in later replies; show its newest saved version.
  const openArtifact = artifactId ? view?.operations.flatMap(o => o.result?.artifacts ?? []).filter(a => a.id === artifactId).sort((a, b) => b.revision - a.revision)[0] : undefined;
  return <div className="user-workspace">
    <aside className="history-sidebar" aria-label="Historia rozmów">{history}</aside>
    <main id="main" tabIndex={-1} className="workspace-chat">
      <Button variant="outline" size="sm" className="mobile-toggle" onClick={() => setDrawer(true)}><Menu aria-hidden="true" />Historia rozmów</Button>
      <section ref={scroll} className="workspace-messages" aria-label="Rozmowa" onScroll={() => { if (!loading && selected.current && scroll.current) positions.current.set(selected.current, scroll.current.scrollTop); }}>
        <h1 className="sr-only">{view?.title || "Rozmowa"}</h1>
        {loading && <p className="history-empty" role="status">Wczytuję rozmowę…</p>}
        {!loading && view && !view.operations.length && <div className="chat-empty">
          <h2>W czym możemy pomóc?</h2>
          <p>Opisz potrzebę, porównaj istniejące rozwiązania lub sprawdź warunki wdrożenia. Możesz pisać albo dyktować przez mikrofon.</p>
          <section className="starters" aria-labelledby="starters-title">
            <h3 id="starters-title">Zacznij od gotowego początku</h3>
            <p className="field-help">Wybierz początek wiadomości, uzupełnij miejsca oznaczone „…” i wyślij.</p>
            <ul className="starters-list">{starters.map(starter => <li key={starter.title}>
              <button type="button" className="starter" disabled={Boolean(pending)} onClick={() => pickStarter(starter.text)}>
                <span className="starter-title">{starter.title}</span>
                <span className="starter-text">{starter.text}</span>
              </button>
            </li>)}</ul>
          </section>
        </div>}
        <div role="log" aria-live="polite" aria-relevant="additions text" aria-label="Wiadomości">{view?.operations.map(operation => <div key={operation.key}>
          <article className="message user"><p>{operation.content}</p></article>
          {operation.status === "completed" && operation.result && <article className="message assistant"><Markdown text={operation.result.answer} />{operation.result.innovations.length > 0 && <p className="innovation-label">Więcej o rozwiązaniach</p>}<div className="innovation-titles">{operation.result.innovations.map(innovation => <Button variant="link" key={innovation.id} onClick={() => openSource(view.id, innovation)}>{innovation.title}</Button>)}</div>{Boolean(operation.result.artifacts?.length) && <p className="innovation-label">Zapisane dokumenty</p>}<div className="innovation-titles">{operation.result.artifacts?.map(artifact => <Button variant="link" key={artifact.id} onClick={() => setArtifactId(artifact.id)}>{artifact.title}</Button>)}</div><SavedMatters matters={operation.result.matters} creator={operation.result.creator} />{Boolean(operation.result.sources?.length) && <details className="answer-sources"><summary>Sprawdź źródła</summary><ul>{operation.result.sources?.map((item, index) => { const url = safeLink(item.url); return <li key={`${item.id}-${index}`}>{url ? <a href={url} target="_blank" rel="noopener noreferrer">{item.title}<span className="sr-only"> (otwiera się w nowej karcie)</span></a> : item.title}{item.publication_date && ` - ${item.publication_date}`}{item.geography && `, ${item.geography}`}{item.page_start && `, str. ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""}`}</li>; })}</ul></details>}</article>}
          {operation.key === last?.key && operation.status === "completed" && !pending && Boolean(operation.result?.suggestions?.length) && <Suggestions label="Co dalej?" items={operation.result!.suggestions!} disabled={loading} onSend={text => void send(undefined, text)} />}
          {operation.status === "processing" && <p className="turn-status" role="status">Przetwarzam<span className="loading-dots" aria-hidden="true"><span /><span /><span /></span></p>}
          {operation.status === "failed" && <div className="turn-failed"><p role="alert">{operation.result?.answer || "Nie udało się uzyskać odpowiedzi. Wiadomość została zachowana."}</p>{last?.key === operation.key && <Button variant="outline" size="sm" disabled={Boolean(pending)} onClick={() => void send(operation)}>Ponów wiadomość</Button>}</div>}
        </div>)}</div>
      </section>
      <div className="composer-area">{creator?.active && <CreatorPanel creator={creator} disabled={Boolean(pending) || loading} onSend={text => void send(undefined, text)} />}{view && <div className="conversation-actions">{view.operations.some(o => o.status === "completed") && <Button variant="outline" size="sm" disabled={Boolean(pending) || loading} onClick={() => setHandoff(true)}>Podsumowanie i kontakt</Button>}</div>}<form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <label className="sr-only" htmlFor="question">Twoja wiadomość</label>
        <Textarea ref={input} id="question" value={view ? drafts[view.id] ?? "" : ""} readOnly={Boolean(pending)} disabled={!view || loading} aria-describedby="speech-status send-status" maxLength={4000} rows={1} placeholder="Napisz lub dyktuj, w czym możemy pomóc…" onChange={event => { edited(event.target.value); if (view) setDrafts(old => ({ ...old, [view.id]: event.target.value })); }} onKeyDown={event => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!sending.current) void send(); }
        }} />
        <div className="composer-actions">
          <Button type="button" size="icon" variant={listening ? "default" : "outline"} className="composer-mic" aria-pressed={listening} aria-controls="question" disabled={!view || loading || Boolean(pending)} aria-label={listening ? "Zatrzymaj dyktowanie" : "Dyktuj wiadomość"} title={listening ? "Zatrzymaj dyktowanie" : "Dyktuj wiadomość"} onClick={() => toggle()}><Mic aria-hidden="true" className="size-5" /></Button>
          <span tabIndex={pending ? 0 : undefined} title={pending ? waitMessage : "Wyślij wiadomość"} aria-label={pending ? waitMessage : undefined}><Button type="submit" size="icon" disabled={!view || loading || !drafts[view.id]?.trim() || Boolean(pending)} aria-label="Wyślij wiadomość"><Send aria-hidden="true" /></Button></span>
        </div>
      </form>
        <div className="workspace-status">
          <p id="speech-status" className={`request-status${notice?.tone === "listening" ? " is-listening" : notice?.tone === "error" ? " is-error" : ""}`} role={notice?.tone === "error" ? "alert" : "status"}>{notice?.text ?? ""}</p>
          <p id="send-status" className={`request-status${error && !pending ? " is-error" : ""}`} role={error && !pending ? "alert" : "status"}>{pending ? waitMessage : error}</p>
          {error && <Button variant="link" onClick={() => { void refresh().catch(handleError); if (selected.current) void read(selected.current).catch(handleError); }}>Odśwież rozmowę</Button>}
        </div>
      </div>
    </main>
    <Dialog open={drawer} onClose={() => setDrawer(false)} title="Historia rozmów" className="history-drawer">{history}</Dialog>
    {handoff && view && <Handoff key={view.id} threadId={view.id} onClose={() => setHandoff(false)} onSessionExpired={handleError} />}
    {source && <Sources key={source.id} innovation={source} onClose={() => setSource(null)} />}
    {openArtifact && view && <Dialog open onClose={() => setArtifactId(null)} title={openArtifact.title}>
      <p className="artifact-type">{artifactTypes[openArtifact.type]}</p>
      <div className="artifact-actions">
        <Button type="button" variant="outline" size="sm" onClick={() => {
          void download(`workspace/conversations/${view.id}/artifacts/${openArtifact.id}/pdf`, `${openArtifact.title}.pdf`)
            .catch(cause => { if (cause instanceof ApiError && cause.status === 401) handleError(cause); else setError("Nie udało się pobrać PDF dokumentu."); });
        }}>Pobierz PDF</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => {
          void api("matters", "POST", {
            title: openArtifact.title,
            type: openArtifact.type,
            content_markdown: openArtifact.content_markdown,
          }).then(() => setError("Zapisano dokument jako sprawę w „Moje sprawy”.")).catch(cause => {
            if (cause instanceof ApiError && cause.status === 401) handleError(cause);
            else setError("Nie udało się zapisać sprawy.");
          });
        }}>Zapisz jako sprawę</Button>
      </div>
      <Markdown text={openArtifact.content_markdown} />
    </Dialog>}
  </div>;
}

/** Clickable messages sent as the user's own; native buttons keep them keyboard accessible. */
function Suggestions({ label, items, disabled, onSend }: { label: string; items: string[]; disabled: boolean; onSend: (text: string) => void }) {
  return <nav className="chat-suggestions" aria-label={label}>
    <p className="chat-suggestions-label" aria-hidden="true">{label}</p>
    <ul>{items.map(item => <li key={item}><Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onSend(item)}>{item}</Button></li>)}</ul>
  </nav>;
}

/** Matters saved by one answer, with a prominent link when the idea creator saved its application input. */
function SavedMatters({ matters, creator }: { matters?: MatterLink[]; creator?: CreatorState | null }) {
  if (!matters?.length) return null;
  const finished = creator && !creator.active && creator.matter_id ? matters.find(m => m.id === creator.matter_id) : undefined;
  return <>
    {finished && <p className="creator-saved">Zapisano zgłoszenie „{finished.title}”. <Link className="creator-saved-link" href={`/matters/${finished.id}`}>Zobacz w Moich sprawach</Link></p>}
    <p className="innovation-label">Zapisane w Moich sprawach</p>
    <ul className="saved-matters">{matters.map(matter => <li key={matter.id}><Link href={`/matters/${matter.id}`}>{matter.title}</Link> <span className="saved-matter-type">({matterTypes[matter.type]})</span></li>)}</ul>
  </>;
}

/** Progress of the opt-in idea creator: states are text, not colour only, and announced politely. */
function CreatorPanel({ creator, disabled, onSend }: { creator: CreatorState; disabled: boolean; onSend: (text: string) => void }) {
  const next = creator.steps.findIndex(step => !step.done);
  const total = creator.steps.length;
  return <section className="creator-panel" aria-labelledby="creator-title">
    <div aria-live="polite">
      <h2 id="creator-title">Kreator zgłoszenia</h2>
      <p className="creator-progress">{next === -1 ? `Wszystkie kroki uzupełnione (${total} z ${total})` : `Krok ${next + 1} z ${total}: ${creator.steps[next].label}`}</p>
      <ol className="creator-steps">{creator.steps.map((step, index) => <li key={step.key} className={step.done ? "is-done" : index === next ? "is-current" : undefined} aria-current={index === next ? "step" : undefined}>
        <span className="creator-step-mark" aria-hidden="true">{step.done ? "✓" : index + 1}</span>
        <span>{step.label}<span className="creator-step-state"> - {step.done ? "uzupełnione" : "do uzupełnienia"}</span></span>
      </li>)}</ol>
    </div>
    <div className="creator-actions">
      <Button size="sm" disabled={disabled} onClick={() => onSend(creatorMessages.finish)}>Zapisz zgłoszenie</Button>
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => onSend(creatorMessages.cancel)}>Zakończ kreator</Button>
    </div>
    <p className="field-help">Jeśli nie znasz odpowiedzi, napisz „nie wiem”. Zakończenie kreatora nie usuwa zebranych informacji.</p>
  </section>;
}
