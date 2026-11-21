"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { session } from "@/features/workspace";
import { limits, sendContactMessage, type ContactField, type ContactInput } from "./api";

type Errors = Partial<Record<ContactField, string>>;

const order: ContactField[] = ["name", "email", "message", "consent"];
const fieldId = (field: ContactField) => `contact-${field}`;
const empty: ContactInput = { name: "", email: "", message: "", consent: false };

const messages: Record<ContactField, string> = {
  name: `Podaj imię i nazwisko (od ${limits.name.min} do ${limits.name.max} znaków, w jednej linii).`,
  email: "Podaj poprawny adres e-mail, na przykład jan.kowalski@example.com.",
  message: `Napisz wiadomość (od ${limits.message.min} do ${limits.message.max} znaków).`,
  consent: "Zaznacz zgodę na przetwarzanie danych, abyśmy mogli odpowiedzieć.",
};

function validate(input: ContactInput): Errors {
  const errors: Errors = {};
  const name = input.name.trim();
  if (name.length < limits.name.min || name.length > limits.name.max) errors.name = messages.name;
  const email = input.email.trim();
  if (email.length > limits.email.max || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = messages.email;
  const message = input.message.trim();
  if (message.length < limits.message.min || message.length > limits.message.max) errors.message = messages.message;
  if (!input.consent) errors.consent = messages.consent;
  return errors;
}

export function ContactPage() {
  const [input, setInput] = useState<ContactInput>(empty);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const failureRef = useRef<HTMLParagraphElement>(null);
  const successRef = useRef<HTMLHeadingElement>(null);
  const invalid = order.filter(field => errors[field]);

  // Logged-in users get their account e-mail prefilled; visitors simply type it.
  useEffect(() => {
    let active = true;
    session().then(user => {
      if (active && user.email) setInput(current => current.email ? current : { ...current, email: user.email! });
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => { if (sentTo) successRef.current?.focus(); }, [sentTo]);

  function change<K extends ContactField>(field: K, value: ContactInput[K]) {
    const next = { ...input, [field]: value };
    setInput(next);
    // Once a field was reported, its message follows the correction instead of waiting for the next submit.
    if (errors[field]) setErrors(current => ({ ...current, [field]: validate(next)[field] }));
  }

  function report(next: Errors) {
    setErrors(next);
    requestAnimationFrame(() => summaryRef.current?.focus());
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure("");
    const found = validate(input);
    if (Object.keys(found).length) { report(found); return; }
    setErrors({});
    setBusy(true);
    try {
      const data = { ...input, name: input.name.trim(), email: input.email.trim(), message: input.message.trim() };
      const result = await sendContactMessage(data);
      if (result.ok) { setSentTo(data.email); setInput(current => ({ ...empty, email: current.email })); return; }
      if (result.status === 422 && result.fields.length) {
        report(Object.fromEntries(result.fields.map(field => [field, messages[field]])));
        return;
      }
      setFailure(result.status === 429
        ? "Wysłano zbyt wiele wiadomości w krótkim czasie. Spróbuj ponownie za minutę."
        : "Nie udało się wysłać wiadomości. Sprawdź połączenie i spróbuj ponownie.");
    } catch {
      setFailure("Nie udało się wysłać wiadomości. Sprawdź połączenie i spróbuj ponownie.");
    } finally { setBusy(false); }
  }

  useEffect(() => { if (failure) failureRef.current?.focus(); }, [failure]);

  const describedBy = (field: ContactField, help?: string) =>
    [help, errors[field] ? `${fieldId(field)}-error` : undefined].filter(Boolean).join(" ") || undefined;
  const fieldError = (field: ContactField) => errors[field]
    ? <span id={`${fieldId(field)}-error`} className="field-error">{errors[field]}</span> : null;

  return <section aria-labelledby="contact-title">
    <div className="page-intro">
      <h1 id="contact-title">Kontakt</h1>
      <p>Masz pytanie, innowację do zgłoszenia albo chcesz współpracować z PCI? Napisz do nas. Odpowiemy na podany adres e-mail.</p>
    </div>
    {sentTo ? <div className="panel contact-sent">
      <h2 ref={successRef} tabIndex={-1}>Dziękujemy, wiadomość została wysłana</h2>
      <p>Zespół PCI odpowie na adres <strong>{sentTo}</strong>.</p>
      <Button variant="outline" onClick={() => {
        setSentTo(null); requestAnimationFrame(() => document.getElementById(fieldId("name"))?.focus());
      }}>Napisz kolejną wiadomość</Button>
    </div> : <div className="panel">
      {invalid.length > 0 && <div ref={summaryRef} tabIndex={-1} role="alert" className="error-summary" aria-labelledby="contact-errors-title">
        <h2 id="contact-errors-title">Popraw {invalid.length === 1 ? "błąd" : "błędy"} w formularzu</h2>
        <ul>{invalid.map(field => <li key={field}><a href={`#${fieldId(field)}`} onClick={event => {
          event.preventDefault(); document.getElementById(fieldId(field))?.focus();
        }}>{errors[field]}</a></li>)}</ul>
      </div>}
      <p ref={failureRef} tabIndex={-1} role="alert" className="form-error">{failure}</p>
      <form onSubmit={submit} noValidate className="tester-form" aria-describedby="contact-required">
        <p id="contact-required" className="field-help contact-required">Wszystkie pola są wymagane.</p>
        <div className="field-block">
          <label htmlFor={fieldId("name")}>Imię i nazwisko</label>
          {fieldError("name")}
          <Input id={fieldId("name")} autoComplete="name" required maxLength={limits.name.max} value={input.name}
            onChange={e => change("name", e.target.value)} disabled={busy}
            aria-invalid={errors.name ? true : undefined} aria-describedby={describedBy("name")} />
        </div>
        <div className="field-block">
          <label htmlFor={fieldId("email")}>E-mail</label>
          {fieldError("email")}
          <Input id={fieldId("email")} type="email" autoComplete="email" spellCheck={false} required maxLength={limits.email.max}
            value={input.email} onChange={e => change("email", e.target.value)} disabled={busy}
            aria-invalid={errors.email ? true : undefined} aria-describedby={describedBy("email")} />
        </div>
        <div className="field-block">
          <label htmlFor={fieldId("message")}>Wiadomość</label>
          <span id="contact-message-help" className="field-help">Opisz krótko, w czym możemy pomóc. Nie podawaj danych o zdrowiu ani innych danych wrażliwych.</span>
          {fieldError("message")}
          <Textarea id={fieldId("message")} required maxLength={limits.message.max} value={input.message}
            onChange={e => change("message", e.target.value)} disabled={busy} className="field-textarea"
            aria-invalid={errors.message ? true : undefined} aria-describedby={describedBy("message", "contact-message-help contact-message-count")} />
          <span id="contact-message-count" className="field-help contact-count">{input.message.length} / {limits.message.max} znaków</span>
        </div>
        <div className="contact-consent">
          {fieldError("consent")}
          <label className="consent" htmlFor={fieldId("consent")}>
            <input id={fieldId("consent")} type="checkbox" required checked={input.consent} onChange={e => change("consent", e.target.checked)}
              disabled={busy} aria-invalid={errors.consent ? true : undefined} aria-describedby={describedBy("consent")} />
            <span>Zgadzam się na przetwarzanie podanych danych (imię i nazwisko, e-mail, treść wiadomości) przez Podkarpackie Centrum Innowacji w celu udzielenia odpowiedzi.</span>
          </label>
        </div>
        <Button type="submit" size="lg" disabled={busy}>{busy ? "Wysyłam…" : "Wyślij wiadomość"}</Button>
        <p role="status" className="sr-only">{busy ? "Wysyłam wiadomość…" : ""}</p>
      </form>
    </div>}
  </section>;
}
