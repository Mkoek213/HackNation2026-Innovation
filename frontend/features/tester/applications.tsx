"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, session } from "@/features/workspace";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { applicationStatusLabels, formatApplicationDate, type TesterApplication } from "./api";

function StatusBadge({ application }: { application: TesterApplication }) {
  return <span className={`application-status application-status-${application.status}`}>{applicationStatusLabels[application.status]}</span>;
}

type ApplyState =
  | { kind: "loading" | "hidden" | "no-profile" | "failed" }
  | { kind: "ready"; application: TesterApplication | null };

/** "Zgłoś chęć pilotażu" section of an innovation dialog; renders nothing for anonymous visitors and admins. */
export function ApplyAsTester({ innovationId, innovationTitle }: { innovationId: string; innovationTitle: string }) {
  const [state, setState] = useState<ApplyState>({ kind: "loading" });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const account = await session();
        if (account.role === "admin") { if (active) setState({ kind: "hidden" }); return; }
        const [profile, applications] = await Promise.all([
          api<{ user_id: number } | null>("volunteers/mine"), api<TesterApplication[]>("tester-applications/mine"),
        ]);
        if (!active) return;
        if (!profile) setState({ kind: "no-profile" });
        else setState({ kind: "ready", application: applications.find(item => item.innovation_id === innovationId) ?? null });
      } catch (cause) {
        if (active) setState({ kind: cause instanceof ApiError && cause.status === 401 ? "hidden" : "failed" });
      }
    }
    void load();
    return () => { active = false; };
  }, [innovationId]);

  async function apply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    try {
      const application = await api<TesterApplication>("tester-applications", "POST", { innovation_id: innovationId, message: message || null });
      setState({ kind: "ready", application }); setMessage("");
      setSuccess("Wysłano zgłoszenie. Pracownicy PCI rozpatrzą je i skontaktują się z Tobą.");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409
        ? "Masz już zgłoszenie do tej innowacji albo nie należysz jeszcze do bazy partnerów."
        : cause instanceof ApiError && cause.status === 404
        ? "Nie znaleziono tej innowacji w bazie."
        : cause instanceof ApiError && cause.status === 422
        ? "Wiadomość może mieć najwyżej 2000 znaków."
        : "Nie udało się wysłać zgłoszenia. Spróbuj ponownie.");
    } finally { setBusy(false); }
  }

  if (state.kind === "loading" || state.kind === "hidden") return null;
  return <section className="apply-tester" aria-labelledby={`apply-${innovationId}`}>
    <h3 id={`apply-${innovationId}`}>Pilotaż lub wdrożenie</h3>
    <p role="status" className="form-success">{success}</p>
    {state.kind === "failed" && <p role="alert" className="form-error">Nie udało się sprawdzić, czy możesz zgłosić chęć pilotażu.</p>}
    {state.kind === "no-profile" && <p>Chcesz przetestować lub wdrożyć tę innowację? <Link href="/tester">Najpierw dołącz do bazy partnerów</Link>.</p>}
    {state.kind === "ready" && state.application && <p>Twoje zgłoszenie: <StatusBadge application={state.application} /></p>}
    {state.kind === "ready" && !state.application && <form onSubmit={apply} className="apply-tester-form">
      <label className="field-block">Wiadomość do PCI (opcjonalnie)
        <Textarea maxLength={2000} value={message} onChange={e => setMessage(e.target.value)} disabled={busy} className="field-textarea" aria-describedby={`apply-help-${innovationId}`} />
        <span id={`apply-help-${innovationId}`} className="field-help">Napisz, w jaki sposób chcesz pilotować lub wdrożyć „{innovationTitle}”.</span>
      </label>
      <p role="alert" className="form-error">{error}</p>
      <Button type="submit" disabled={busy}>{busy ? "Wysyłam…" : "Zgłoś chęć pilotażu"}</Button>
    </form>}
  </section>;
}

/** "Moje zgłoszenia" list on the tester page, with withdrawal of pending applications. */
export function MyApplications() {
  const [applications, setApplications] = useState<TesterApplication[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    api<TesterApplication[]>("tester-applications/mine")
      .then(items => { if (active) setApplications(items); })
      .catch(() => { if (active) { setApplications([]); setError("Nie udało się wczytać Twoich zgłoszeń. Odśwież stronę."); } });
    return () => { active = false; };
  }, []);

  async function withdraw(application: TesterApplication) {
    setBusy(true); setError(""); setMessage("");
    try {
      await api(`tester-applications/mine/${application.id}`, "DELETE");
      setApplications(items => (items ?? []).filter(item => item.id !== application.id));
      setMessage(`Wycofano zgłoszenie do innowacji „${application.innovation_title}”.`);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409
        ? "To zgłoszenie zostało już rozpatrzone i nie można go wycofać."
        : "Nie udało się wycofać zgłoszenia. Spróbuj ponownie.");
    } finally { setBusy(false); }
  }

  return <section className="panel my-applications" aria-labelledby="my-applications-title">
    <h2 id="my-applications-title">Moje zgłoszenia</h2>
    <p role="alert" className="form-error">{error}</p>
    <p role="status" className="form-success">{message}</p>
    {applications === null ? <p className="field-help">Wczytuję…</p>
      : !applications.length ? <p className="field-help">Nie masz jeszcze zgłoszeń. Wybierz innowację w <Link href="/knowledge/innovations">bazie innowacji</Link> i kliknij „Zgłoś chęć pilotażu”.</p>
      : <ul className="application-list">{applications.map(application => <li key={application.id}>
        <div className="application-head">
          <span className="application-title">{application.innovation_title}</span>
          <StatusBadge application={application} />
        </div>
        <p className="candidate-meta">
          Zgłoszenie: {formatApplicationDate(application.created_at)}
          {application.source === "admin" && " · dodane przez PCI"}
          {application.decided_at && ` · decyzja: ${formatApplicationDate(application.decided_at)}`}
        </p>
        {application.status === "pending" && <Button variant="outline" size="sm" disabled={busy}
          onClick={() => void withdraw(application)} aria-label={`Wycofaj zgłoszenie do innowacji ${application.innovation_title}`}>Wycofaj</Button>}
      </li>)}</ul>}
  </section>;
}
