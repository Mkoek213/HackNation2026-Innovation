"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError, session, type User } from "@/features/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { MyApplications } from "./applications";

type Label = { id: number; name: string };
type Option = { id: string; label: string };
type Options = { roles: Option[]; interests: Option[] };
type Profile = { user_id: number; email: string; phone: string; description: string; roles: string[]; interests: string[]; tags: Label[]; tagging_status: string; created_at: string };
type Pool = { total: number; items: Profile[] };
const pageSize = 20;

export function VolunteerPage({ admin = false }: { admin?: boolean }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [description, setDescription] = useState("");
  const [consent, setConsent] = useState(false);
  const [roles, setRoles] = useState<string[]>([]);
  const [interests, setInterests] = useState<string[]>([]);
  const [options, setOptions] = useState<Options>({ roles: [], interests: [] });
  const [role, setRole] = useState("");
  const [interest, setInterest] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [labels, setLabels] = useState<Label[]>([]);
  const [pool, setPool] = useState<Pool>({ total: 0, items: [] });
  const [offset, setOffset] = useState(0);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);

  function fail(cause: unknown) {
    setInvalid(false);
    if (cause instanceof ApiError && cause.status === 401) {
      setUser(null); setPool({ total: 0, items: [] }); setProfile(null);
      setEmail(""); setPhone(""); setDescription(""); setConsent(false); setRoles([]); setInterests([]);
      setError("Sesja wygasła. Zaloguj się ponownie.");
    } else setError(cause instanceof ApiError && cause.status === 403
      ? "Konto administratora nie może zgłosić się jako partner pilotażu."
      : cause instanceof ApiError && cause.status === 422
      ? "Sprawdź adres e-mail, numer telefonu, wybrane odpowiedzi i opis (maksymalnie 2000 znaków)."
      : "Nie udało się wykonać działania. Spróbuj ponownie.");
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const account = await session();
        if (!active) return;
        setUser(account);
        if (admin) {
          if (account.role !== "admin") return;
          const [topics, choices, candidates] = await Promise.all([
            api<Label[]>("volunteers/tags"), api<Options>("volunteers/options"), api<Pool>("volunteers?limit=20"),
          ]);
          if (active) { setLabels(topics); setOptions(choices); setPool(candidates); }
        } else {
          if (account.role === "admin") return;
          const [choices, saved] = await Promise.all([api<Options>("volunteers/options"), api<Profile | null>("volunteers/mine")]);
          if (active) {
            setOptions(choices); setRoles(saved?.roles || []); setInterests(saved?.interests || []);
            setProfile(saved); setEmail(saved?.email || account.email || "");
            setPhone(saved?.phone || ""); setDescription(saved?.description || ""); setConsent(Boolean(saved));
          }
        }
      } catch (cause) {
        if (active) {
          if (cause instanceof ApiError && cause.status === 401) setUser(null);
          else { setLoadFailed(true); setError("Nie udało się wczytać danych. Odśwież stronę, aby spróbować ponownie."); }
        }
      } finally { if (active) setReady(true); }
    }
    void load();
    return () => { active = false; };
  }, [admin]);

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setMessage(""); setInvalid(false);
    if (!roles.length || !interests.length) {
      setError("Zaznacz co najmniej jedną odpowiedź w pytaniu „Kim jesteś?” i w pytaniu „W jakich sektorach możesz pilotować?”.");
      return;
    }
    setBusy(true);
    try {
      const saved = await api<Profile>("volunteers/mine", "PUT", { email, phone, description, roles, interests, consent });
      setProfile(saved); setConfirmWithdraw(false);
      setMessage("Zapisano profil. Pracownicy PCI mogą skontaktować się z Tobą w sprawie pilotaży.");
    } catch (cause) {
      fail(cause);
      if (cause instanceof ApiError && cause.status === 422) setInvalid(true);
    } finally { setBusy(false); }
  }

  async function withdraw() {
    setBusy(true); setError(""); setMessage("");
    try {
      await api("volunteers/mine", "DELETE"); setProfile(null); setEmail(user?.email || ""); setPhone(""); setDescription("");
      setRoles([]); setInterests([]); setConsent(false); setConfirmWithdraw(false); setMessage("Usunięto profil z bazy partnerów. Twoje konto pozostaje aktywne.");
    } catch (cause) { fail(cause); } finally { setBusy(false); }
  }

  async function search(nextOffset: number) {
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ q: query, limit: String(pageSize), offset: String(nextOffset) });
      if (tag) params.set("tag_id", tag);
      if (role) params.set("role", role);
      if (interest) params.set("interest", interest);
      setPool(await api<Pool>(`volunteers?${params}`)); setOffset(nextOffset);
    } catch (cause) { fail(cause); } finally { setBusy(false); }
  }

  if (!ready) return <p role="status" className="page-status">Wczytuję…</p>;
  if (loadFailed) return <div className="page-status"><p role="alert">{error}</p><Button onClick={() => window.location.reload()}>Spróbuj ponownie</Button></div>;
  if (!user) return <section className="page-intro"><h1>Wybierz rolę</h1><p>Aby zgłosić się jako partner pilotażu, najpierw wybierz rolę i zaloguj się.</p><p role="alert" className="form-error">{error}</p><Button nativeButton={false} render={<Link href="/rozmowa" />}>Wybierz rolę</Button></section>;
  if (admin && user.role !== "admin") return <p role="alert" className="page-status">Ta część platformy jest dostępna tylko dla administratorów.</p>;
  if (!admin && user.role === "admin") return <section className="page-intro"><h1>Zgłoś gotowość do pilotażu</h1><p role="alert">Konto administratora nie może zgłosić się jako partner pilotażu.</p><Button nativeButton={false} render={<Link href="/administration/testers" />}>Przejdź do panelu administratora</Button></section>;

  return <section aria-labelledby="volunteer-title">
    <div className="page-intro">
      <h1 id="volunteer-title">{admin ? "Baza partnerów" : "Zgłoś gotowość do pilotażu"}</h1>
      <p>{admin ? "Instytucje, firmy i eksperci gotowi pilotować, wdrażać lub finansować innowacje. Najnowsze zgłoszenia są na górze." : "Reprezentujesz szkołę, uczelnię, samorząd, firmę albo fundusz i chcesz przetestować, wdrożyć lub sfinansować innowację? Dołącz do bazy partnerów. Skontaktujemy się, gdy pojawi się pasujące rozwiązanie."}</p>
    </div>
    <p id="volunteer-error" ref={errorRef} tabIndex={-1} role="alert" className="form-error">{error}</p>
    <p role="status" className="form-success">{message}</p>
    {admin ? <>
      <form className="admin-filters admin-filters-wide" onSubmit={event => { event.preventDefault(); void search(0); }}>
        <label className="field-block">Szukaj w opisach<Input type="search" value={query} onChange={e => setQuery(e.target.value)} maxLength={200} disabled={busy} /></label>
        <label className="field-block">Temat<select className="select" value={tag} onChange={e => setTag(e.target.value)} disabled={busy}><option value="">Wszystkie tematy</option>{labels.map(label => <option key={label.id} value={label.id}>{label.name}</option>)}</select></label>
        <label className="field-block">Typ partnera<select className="select" value={role} onChange={e => setRole(e.target.value)} disabled={busy}><option value="">Wszyscy</option>{options.roles.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <label className="field-block">Sektor<select className="select" value={interest} onChange={e => setInterest(e.target.value)} disabled={busy}><option value="">Wszystkie sektory</option>{options.interests.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
        <Button type="submit" disabled={busy}>{busy ? "Wczytuję…" : "Szukaj"}</Button>
      </form>
      <p role="status" className="result-count">Liczba zgłoszeń: {pool.total}</p>
      <ul className="candidate-list" aria-label="Zgłoszenia partnerów">{pool.items.map(candidate => <li key={candidate.user_id} className="panel">
        <div className="candidate-contact"><a href={`mailto:${candidate.email}`}>{candidate.email}</a><a href={`tel:${candidate.phone.replace(/[^+0-9]/g, "")}`}>{candidate.phone}</a></div>
        {candidate.description && <p className="candidate-description">{candidate.description}</p>}
        <CandidateTags candidate={candidate} options={options} />
        <p className="candidate-meta">Zgłoszenie: {new Date(candidate.created_at).toLocaleDateString("pl-PL")}{candidate.description && candidate.tagging_status !== "completed" && ". Tematy z opisu nie zostały jeszcze w pełni oznaczone."}</p>
      </li>)}</ul>
      {!pool.items.length && <p className="panel empty-state">Brak zgłoszeń spełniających kryteria.</p>}
      <div className="pager"><Button variant="outline" disabled={busy || offset === 0} onClick={() => void search(offset - pageSize)}>Poprzednie</Button><Button variant="outline" disabled={busy || offset + pageSize >= pool.total} onClick={() => void search(offset + pageSize)}>Następne</Button></div>
    </> : <div className="panel">
      {profile && <p className="tester-status">Jesteś w bazie partnerów. Udział w każdym pilotażu ustalisz osobno.</p>}
      <form onSubmit={save} className="tester-form">
        <label className="field-block">E-mail<Input type="email" required autoComplete="email" spellCheck={false} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} aria-invalid={invalid || undefined} aria-describedby={invalid ? "volunteer-error" : undefined} /></label>
        <label className="field-block">Telefon<Input type="tel" required autoComplete="tel" spellCheck={false} minLength={7} maxLength={32} value={phone} onChange={e => setPhone(e.target.value)} disabled={busy} aria-invalid={invalid || undefined} aria-describedby={invalid ? "volunteer-error" : undefined} /></label>
        <TagChoices legend="Kim jesteś?" name="roles" options={options.roles} selected={roles} onChange={setRoles} disabled={busy} />
        <TagChoices legend="W jakich sektorach możesz pilotować?" name="interests" options={options.interests} selected={interests} onChange={setInterests} disabled={busy} />
        <label className="field-block">Krótko o organizacji (opcjonalnie)<Textarea maxLength={2000} value={description} onChange={e => setDescription(e.target.value)} disabled={busy} className="field-textarea" aria-invalid={invalid || undefined} aria-describedby={invalid ? "volunteer-error description-help" : "description-help"} /><span id="description-help" className="field-help">Nazwa organizacji, doświadczenie i to, czego szukacie: rozwiązania do wdrożenia, testu lub inwestycji.</span></label>
        <label className="consent"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy} /><span>Chcę dołączyć do bazy partnerów Radaru innowacji i zgadzam się na kontakt w sprawie pilotaży i wdrożeń innowacji.</span></label>
        <Button type="submit" size="lg" disabled={busy}>{busy ? "Proszę czekać…" : profile ? "Zapisz zmiany" : "Dołącz do bazy"}</Button>
      </form>
      {profile && <div className="withdraw">
        {!confirmWithdraw ? <Button variant="link" disabled={busy} onClick={() => setConfirmWithdraw(true)}>Wypisz się z bazy partnerów</Button> : <><p>Usunąć Twój profil z bazy partnerów razem ze zgłoszeniami do pilotaży? Konto pozostanie aktywne.</p><div className="withdraw-actions"><Button variant="destructive" disabled={busy} onClick={() => void withdraw()}>Usuń profil partnera</Button><Button variant="outline" disabled={busy} onClick={() => setConfirmWithdraw(false)}>Anuluj</Button></div></>}
      </div>}
    </div>}
    {!admin && profile && <MyApplications />}
  </section>;
}

function TagChoices({ legend, name, options, selected, onChange, disabled }: {
  legend: string; name: string; options: Option[]; selected: string[]; onChange: (next: string[]) => void; disabled: boolean;
}) {
  return <fieldset className="tag-fieldset">
    <legend>{legend} <span className="field-help">Zaznacz co najmniej jedną odpowiedź.</span></legend>
    <div className="tag-options">{options.map(option => <label key={option.id} className="consent">
      <input type="checkbox" name={name} value={option.id} checked={selected.includes(option.id)} disabled={disabled}
        onChange={e => onChange(e.target.checked ? [...selected, option.id] : selected.filter(id => id !== option.id))} />
      <span>{option.label}</span>
    </label>)}</div>
  </fieldset>;
}

function CandidateTags({ candidate, options }: { candidate: Profile; options: Options }) {
  const label = (list: Option[], id: string) => list.find(option => option.id === id)?.label || id;
  if (!candidate.roles.length && !candidate.interests.length && !candidate.tags.length) return null;
  return <dl className="candidate-taglists">
    {candidate.roles.length > 0 && <div><dt>Kim jest</dt><dd className="candidate-tags">{candidate.roles.map(id => <Badge key={id}>{label(options.roles, id)}</Badge>)}</dd></div>}
    {candidate.interests.length > 0 && <div><dt>Sektory</dt><dd className="candidate-tags">{candidate.interests.map(id => <Badge key={id} variant="outline">{label(options.interests, id)}</Badge>)}</dd></div>}
    {candidate.tags.length > 0 && <div><dt>Tematy z opisu</dt><dd className="candidate-tags">{candidate.tags.map(topic => <Badge key={topic.id} variant="secondary">{topic.name}</Badge>)}</dd></div>}
  </dl>;
}
