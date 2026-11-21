"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/features/workspace";
import { applicationStatusLabels, formatApplicationDate, type ApplicationStatus, type TesterApplicationAdmin } from "@/features/tester";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  applicationsPageSize, type ApplicationList, type InnovationOption, type PoolTester, type TagOption, type TesterOptions,
} from "./api";
import styles from "./administration.module.css";

type Filters = { status: "" | ApplicationStatus; innovation: string };
type Pool = { total: number; items: PoolTester[] };

function label(list: TagOption[], id: string) {
  return list.find(option => option.id === id)?.label || id;
}

function TesterTags({ tester, options }: { tester: Pick<PoolTester, "roles" | "interests" | "tags">; options: TesterOptions }) {
  if (!tester.roles.length && !tester.interests.length && !tester.tags.length) return null;
  return <dl className="candidate-taglists">
    {tester.roles.length > 0 && <div><dt>Typ partnera</dt><dd className="candidate-tags">{tester.roles.map(id => <Badge key={id}>{label(options.roles, id)}</Badge>)}</dd></div>}
    {tester.interests.length > 0 && <div><dt>Sektory</dt><dd className="candidate-tags">{tester.interests.map(id => <Badge key={id} variant="outline">{label(options.interests, id)}</Badge>)}</dd></div>}
    {tester.tags.length > 0 && <div><dt>Tematy z opisu</dt><dd className="candidate-tags">{tester.tags.map(topic => <Badge key={topic.id} variant="secondary">{topic.name}</Badge>)}</dd></div>}
  </dl>;
}

function Contact({ email, phone }: { email: string; phone: string }) {
  return <div className="candidate-contact"><a href={`mailto:${email}`}>{email}</a><a href={`tel:${phone.replace(/[^+0-9]/g, "")}`}>{phone}</a></div>;
}

export function ApplicationsView() {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [innovations, setInnovations] = useState<InnovationOption[]>([]);
  const [options, setOptions] = useState<TesterOptions>({ roles: [], interests: [] });
  const [draft, setDraft] = useState<Filters>({ status: "", innovation: "" });
  const [filters, setFilters] = useState<Filters>({ status: "", innovation: "" });
  const [list, setList] = useState<ApplicationList>({ total: 0, items: [] });
  const [offset, setOffset] = useState(0);

  const [target, setTarget] = useState("");
  const [role, setRole] = useState("");
  const [interest, setInterest] = useState("");
  const [pool, setPool] = useState<Pool | null>(null);
  const [poolOffset, setPoolOffset] = useState(0);

  function fail(cause: unknown, fallback: string) {
    setError(cause instanceof ApiError && cause.status === 401 ? "Sesja wygasła. Zaloguj się ponownie."
      : cause instanceof ApiError && cause.status === 404 ? "Nie znaleziono zgłoszenia, partnera lub innowacji. Odśwież widok."
      : cause instanceof ApiError && cause.status === 503 ? "Baza wiedzy jest chwilowo niedostępna. Spróbuj ponownie później."
      : fallback);
  }

  function applicationsQuery(next: Filters, nextOffset: number) {
    const params = new URLSearchParams({ limit: String(applicationsPageSize), offset: String(nextOffset) });
    if (next.status) params.set("status", next.status);
    if (next.innovation) params.set("innovation_id", next.innovation);
    return `tester-applications?${params}`;
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [applications, choices] = await Promise.all([
          api<ApplicationList>(`tester-applications?limit=${applicationsPageSize}`), api<TesterOptions>("volunteers/options"),
        ]);
        if (!active) return;
        setList(applications); setOptions(choices);
      } catch { if (active) setError("Nie udało się wczytać zgłoszeń. Odśwież stronę."); }
      try {
        const items = await api<InnovationOption[]>("api/v1/knowledge/innovations");
        if (active) setInnovations([...items].sort((a, b) => a.title.localeCompare(b.title, "pl")));
      } catch {
        if (active) setError("Nie udało się wczytać listy innowacji z bazy wiedzy.");
      } finally { if (active) setReady(true); }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function showApplications(next: Filters, nextOffset: number) {
    setBusy(true); setError("");
    try {
      setList(await api<ApplicationList>(applicationsQuery(next, nextOffset)));
      setFilters(next); setOffset(nextOffset);
    } catch (cause) { fail(cause, "Nie udało się wczytać zgłoszeń. Spróbuj ponownie."); } finally { setBusy(false); }
  }

  async function decide(application: TesterApplicationAdmin, status: "approved" | "rejected") {
    setBusy(true); setError(""); setMessage("");
    try {
      const updated = await api<TesterApplicationAdmin>(`tester-applications/${application.id}`, "PATCH", { status });
      setList(current => ({ ...current, items: current.items.map(item => item.id === updated.id ? updated : item) }));
      setMessage(`${status === "approved" ? "Zatwierdzono" : "Odrzucono"} zgłoszenie ${application.email} do innowacji „${application.innovation_title}”.`);
    } catch (cause) { fail(cause, "Nie udało się zapisać decyzji. Spróbuj ponownie."); } finally { setBusy(false); }
  }

  function chooseTarget(id: string) {
    setTarget(id); setPool(null);
    // Default the sector filter to the innovation's main sector, so matching partners show first.
    setInterest(innovations.find(item => item.id === id)?.primary_category ?? "");
  }

  async function searchTesters(nextOffset: number) {
    setBusy(true); setError(""); setMessage("");
    try {
      const params = new URLSearchParams({ limit: String(applicationsPageSize), offset: String(nextOffset) });
      if (role) params.set("role", role);
      if (interest) params.set("interest", interest);
      setPool(await api<Pool>(`volunteers?${params}`)); setPoolOffset(nextOffset);
    } catch (cause) { fail(cause, "Nie udało się wyszukać partnerów. Spróbuj ponownie."); } finally { setBusy(false); }
  }

  async function assign(tester: PoolTester) {
    const innovation = innovations.find(item => item.id === target);
    if (!innovation) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api<TesterApplicationAdmin>("tester-applications/assign", "POST", { user_id: tester.user_id, innovation_id: innovation.id });
      setMessage(`Dodano ${tester.email} jako zatwierdzonego partnera pilotażu innowacji „${innovation.title}”.`);
      setList(await api<ApplicationList>(applicationsQuery(filters, offset)));
    } catch (cause) { fail(cause, "Nie udało się dodać partnera. Spróbuj ponownie."); } finally { setBusy(false); }
  }

  if (!ready) return <p role="status" className="page-status">Wczytuję…</p>;
  const targetTitle = innovations.find(item => item.id === target)?.title;

  return <section aria-labelledby="applications-title">
    <div className="page-intro">
      <h1 id="applications-title">Zgłoszenia pilotaży</h1>
      <p>Innowacje z bazy i partnerzy, którzy chcą je pilotować lub wdrożyć. Zatwierdź lub odrzuć zgłoszenie albo dodaj partnera samodzielnie.</p>
    </div>
    <p role="alert" className="form-error">{error}</p>
    <p role="status" className="form-success">{message}</p>

    <form className="admin-filters admin-filters-wide" onSubmit={event => { event.preventDefault(); void showApplications(draft, 0); }}>
      <label className="field-block">Status<select className="select" value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value as Filters["status"] })} disabled={busy}>
        <option value="">Wszystkie</option>
        {(Object.keys(applicationStatusLabels) as ApplicationStatus[]).map(status => <option key={status} value={status}>{applicationStatusLabels[status]}</option>)}
      </select></label>
      <label className="field-block">Innowacja<select className="select" value={draft.innovation} onChange={e => setDraft({ ...draft, innovation: e.target.value })} disabled={busy}>
        <option value="">Wszystkie innowacje</option>
        {innovations.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select></label>
      <Button type="submit" disabled={busy}>{busy ? "Wczytuję…" : "Pokaż"}</Button>
    </form>
    <p role="status" className="result-count">Liczba zgłoszeń: {list.total}</p>
    <ul className="candidate-list" aria-label="Zgłoszenia do testowania innowacji">{list.items.map(application => <li key={application.id} className="panel">
      <div className="application-head">
        <span className="application-title">{application.innovation_title}</span>
        <span className={`application-status application-status-${application.status}`}>{applicationStatusLabels[application.status]}</span>
        {application.source === "admin" && <span className="field-help">dodany przez PCI</span>}
      </div>
      <Contact email={application.email} phone={application.phone} />
      <TesterTags tester={application} options={options} />
      {application.message && <p className="candidate-description">{application.message}</p>}
      <p className="candidate-meta">Zgłoszenie: {formatApplicationDate(application.created_at)}{application.decided_at && ` · decyzja: ${formatApplicationDate(application.decided_at)}`}</p>
      <div className={styles.applicationActions}>
        <Button disabled={busy || application.status === "approved"} onClick={() => void decide(application, "approved")}
          aria-label={`Zatwierdź zgłoszenie ${application.email} do innowacji ${application.innovation_title}`}>Zatwierdź</Button>
        <Button variant="outline" disabled={busy || application.status === "rejected"} onClick={() => void decide(application, "rejected")}
          aria-label={`Odrzuć zgłoszenie ${application.email} do innowacji ${application.innovation_title}`}>Odrzuć</Button>
      </div>
    </li>)}</ul>
    {!list.items.length && <p className="panel empty-state">Brak zgłoszeń spełniających kryteria.</p>}
    <div className="pager">
      <Button variant="outline" disabled={busy || offset === 0} onClick={() => void showApplications(filters, offset - applicationsPageSize)}>Poprzednie</Button>
      <Button variant="outline" disabled={busy || offset + applicationsPageSize >= list.total} onClick={() => void showApplications(filters, offset + applicationsPageSize)}>Następne</Button>
    </div>

    <section className={`panel ${styles.assign}`} aria-labelledby="assign-title">
      <h2 id="assign-title">Dodaj partnera do innowacji</h2>
      <p className="field-help">Wybierz innowację i wyszukaj partnerów według typu i sektora. Dodany partner ma od razu zatwierdzone zgłoszenie.</p>
      <form className="admin-filters admin-filters-wide" onSubmit={event => { event.preventDefault(); void searchTesters(0); }}>
        <label className="field-block">Innowacja<select className="select" required value={target} onChange={e => chooseTarget(e.target.value)} disabled={busy}>
          <option value="">Wybierz innowację</option>
          {innovations.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select></label>
        <label className="field-block">Typ partnera<select className="select" value={role} onChange={e => setRole(e.target.value)} disabled={busy}>
          <option value="">Wszyscy</option>
          {options.roles.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select></label>
        <label className="field-block">Sektor<select className="select" value={interest} onChange={e => setInterest(e.target.value)} disabled={busy}>
          <option value="">Wszystkie sektory</option>
          {options.interests.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select></label>
        <Button type="submit" disabled={busy || !target}>{busy ? "Wczytuję…" : "Szukaj partnerów"}</Button>
      </form>
      {pool && <>
        <p role="status" className="result-count">Liczba partnerów: {pool.total}</p>
        <ul className="candidate-list" aria-label={`Partnerzy do dodania do innowacji ${targetTitle ?? ""}`}>{pool.items.map(tester => <li key={tester.user_id} className="panel">
          <Contact email={tester.email} phone={tester.phone} />
          <TesterTags tester={tester} options={options} />
          <Button disabled={busy || !target} onClick={() => void assign(tester)}
            aria-label={`Dodaj ${tester.email} do innowacji ${targetTitle ?? ""}`}>Dodaj</Button>
        </li>)}</ul>
        {!pool.items.length && <p className="empty-state">Brak partnerów spełniających kryteria.</p>}
        <div className="pager">
          <Button variant="outline" disabled={busy || poolOffset === 0} onClick={() => void searchTesters(poolOffset - applicationsPageSize)}>Poprzedni partnerzy</Button>
          <Button variant="outline" disabled={busy || poolOffset + applicationsPageSize >= pool.total} onClick={() => void searchTesters(poolOffset + applicationsPageSize)}>Następni partnerzy</Button>
        </div>
      </>}
    </section>
  </section>;
}
