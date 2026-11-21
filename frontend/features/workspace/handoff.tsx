"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "./api";

type Draft = { recipient: string; subject: string; packet: string;
  staff: { name: string; email: string }[] };

export function Handoff({ threadId, onClose, onSessionExpired }: {
  threadId: number; onClose: () => void; onSessionExpired: (error: unknown) => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [copying, setCopying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const preview = useRef<HTMLDetailsElement>(null);
  const message = useRef<HTMLDivElement>(null);
  const body = draft ? `Dzień dobry,

proszę o konsultację opisanej poniżej sprawy i wskazanie możliwych kolejnych kroków.

Z poważaniem
[Imię / nazwa instytucji do uzupełnienia]

---
Podsumowanie rozmowy w Radarze innowacji

${draft.packet.trim()}` : "";

  useEffect(() => {
    let active = true;
    api<Draft>(`workspace/conversations/${threadId}/handoff`).then(data => {
      if (active) { setDraft({ ...data, packet: data.packet ?? "", staff: data.staff ?? [] }); setError(""); }
    }).catch(cause => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 401) onSessionExpired(cause);
      setError(cause instanceof ApiError && cause.status === 409
        ? "Poczekaj na zakończenie odpowiedzi, a następnie spróbuj ponownie."
        : "Nie udało się przygotować podsumowania. Spróbuj ponownie.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [threadId, attempt, onSessionExpired]);

  async function copy() {
    if (!draft || copying) return;
    setCopying(true); setError("");
    try {
      await navigator.clipboard.writeText(`Do: ${draft.recipient.trim()}\nTemat: ${draft.subject}\n\n${body}`);
      setStatus("Skopiowano całą wiadomość z podsumowaniem. Wklej ją do swojej poczty.");
    } catch {
      if (preview.current && message.current) {
        preview.current.open = true;
        message.current.focus();
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(message.current);
        selection?.removeAllRanges(); selection?.addRange(range);
      }
      setStatus("Zaznaczono treść wiadomości w podglądzie. Skopiuj ją do swojej poczty.");
    } finally { setCopying(false); }
  }

  return <Dialog open onClose={onClose} title="Podsumowanie i kontakt z PCI" className="handoff-dialog">
    <p className="handoff-lead">Sprawdź wiadomość i adres odbiorcy. Podsumowanie znajduje się w dalszej części e-maila. Treść i podpis możesz zmienić w swojej poczcie przed wysłaniem.</p>
    {loading && <p role="status">Przygotowuję podsumowanie…</p>}
    {error && <div><p role="alert">{error}</p>{!draft && <Button variant="outline" disabled={loading} onClick={() => { setLoading(true); setAttempt(n => n + 1); }}>Spróbuj ponownie</Button>}</div>}
    {draft && <form className="handoff-form" onSubmit={event => {
      event.preventDefault();
      setError("");
      window.location.href = `mailto:${encodeURIComponent(draft.recipient.trim())}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(body)}`;
      setStatus("Sprawdź szkic w swojej poczcie, uzupełnij podpis i wyślij wiadomość. Jeśli poczta się nie otworzyła lub brakuje części treści, użyj przycisku „Kopiuj wiadomość”.");
    }}>
      <label htmlFor="radar-recipient">Adres pracownika PCI</label>
      <Input id="radar-recipient" type="email" list="radar-staff-emails" required maxLength={254} autoComplete="email" value={draft.recipient} onChange={event => { setDraft({ ...draft, recipient: event.target.value }); setStatus(""); }} />
      <datalist id="radar-staff-emails">{draft.staff.map(person => <option key={person.email} value={person.email} label={person.name} />)}</datalist>
      <label htmlFor="radar-subject">Temat</label>
      <Input id="radar-subject" required maxLength={200} pattern="[^\r\n]+" value={draft.subject} onChange={event => { setDraft({ ...draft, subject: event.target.value }); setStatus(""); }} />
      <details ref={preview} className="handoff-preview"><summary>Podgląd wiadomości</summary><div ref={message} tabIndex={-1} className="handoff-packet">{body}</div></details>
      <div className="handoff-actions">
        <Button type="submit" disabled={!draft.packet.trim()}>Otwórz pocztę</Button>
        <Button type="button" variant="outline" disabled={copying || !draft.packet.trim()} onClick={() => void copy()}>{copying ? "Kopiuję…" : "Kopiuj wiadomość"}</Button>
      </div>
      <p role="status" className="handoff-help">{status || "Otworzysz szkic w swojej poczcie z podsumowaniem w treści. Wiadomość wyślesz po jej sprawdzeniu."}</p>
    </form>}
  </Dialog>;
}
