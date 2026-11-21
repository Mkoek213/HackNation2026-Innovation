"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "@/features/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loadStats, type Period, type Stats } from "./api";
import styles from "./administration.module.css";
import { TopicCharts, TrendChange } from "./topic-charts";

const defaultDays = 30;

function utcDay(date: Date) { return date.toISOString().slice(0, 10); }
function defaultPeriod(): Period {
  const today = new Date();
  return { from: utcDay(new Date(today.getTime() - (defaultDays - 1) * 86_400_000)), to: utcDay(today) };
}
function formatDay(day: string) { return new Date(`${day}T00:00:00Z`).toLocaleDateString("pl-PL", { timeZone: "UTC" }); }
function formatNumber(value: number) { return value.toLocaleString("pl-PL"); }

function errorMessage(cause: unknown) {
  if (!(cause instanceof ApiError)) return "Nie udało się połączyć z serwerem. Sprawdź połączenie i spróbuj ponownie.";
  if (cause.status === 401) return "Sesja wygasła. Zaloguj się ponownie, aby zobaczyć statystyki.";
  if (cause.status === 403) return "Statystyki są dostępne tylko dla administratorów.";
  if (cause.status === 422) return "Sprawdź daty: data końcowa nie może być wcześniejsza niż początkowa, a okres nie może być dłuższy niż 366 dni.";
  if (cause.status === 503) return "Serwer statystyk jest teraz niedostępny. Spróbuj ponownie za chwilę.";
  return "Nie udało się wczytać statystyk. Spróbuj ponownie.";
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className={styles.metric}><dt>{label}</dt><dd>{formatNumber(value)}</dd></div>;
}

function Block({ id, title, lead, children }: { id: string; title: string; lead?: ReactNode; children: ReactNode }) {
  return <section aria-labelledby={id} className={`panel ${styles.block}`}>
    <h2 id={id}>{title}</h2>
    {lead && <p className={styles.lead}>{lead}</p>}
    {children}
  </section>;
}

function Table({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  const align = (index: number) => index ? styles.num : undefined;
  return <div className={styles.tableScroll} role="region" aria-label={caption} tabIndex={0}>
    <table className={styles.table}>
      <caption className="sr-only">{caption}</caption>
      <thead><tr>{head.map((cell, index) => <th key={cell} scope="col" className={align(index)}>{cell}</th>)}</tr></thead>
      <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, index) => index
        ? <td key={index} className={align(index)}>{cell}</td>
        : <th key={index} scope="row">{cell}</th>)}</tr>)}</tbody>
    </table>
  </div>;
}

function Disclosure({ summary, children }: { summary: string; children: ReactNode }) {
  return <details className={styles.daily}>
    <summary>{summary}</summary>
    {children}
  </details>;
}

function Daily({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return <Disclosure summary="Dane dzienne"><Table caption={caption} head={head} rows={rows} /></Disclosure>;
}

export function AnalyticsView() {
  const [draft, setDraft] = useState<Period>(defaultPeriod);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  async function refresh(period: Period) {
    setBusy(true); setError("");
    try { setStats(await loadStats(period)); } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }

  useEffect(() => {
    let active = true;
    loadStats(defaultPeriod()).then(
      data => { if (active) setStats(data); },
      cause => { if (active) setError(errorMessage(cause)); },
    ).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, []);

  function reset() { const period = defaultPeriod(); setDraft(period); void refresh(period); }

  const period = stats?.site.period;
  const tagRows = stats ? stats.tags.items.flatMap(tag => [
    [tag.name, formatNumber(tag.conversations), formatNumber(tag.unique_people), formatNumber(tag.no_answer)],
    ...tag.subtags.filter(subtag => subtag.conversations).map(subtag => [
      <span key="name" className={styles.subrow}>{subtag.name}</span>, formatNumber(subtag.conversations), formatNumber(subtag.unique_people), formatNumber(subtag.no_answer),
    ]),
  ]) : [];

  return <section aria-labelledby="analytics-title">
    <div className="page-intro">
      <h1 id="analytics-title">Analityka</h1>
      <p>O co pytają mieszkańcy, które tematy rosną i gdzie brakuje odpowiedzi. Dni liczone są według czasu UTC.</p>
    </div>

    <form className="admin-filters" onSubmit={event => { event.preventDefault(); void refresh(draft); }}>
      <label className="field-block">Od<Input type="date" required value={draft.from} onChange={e => setDraft({ ...draft, from: e.target.value })} disabled={busy} /></label>
      <label className="field-block">Do<Input type="date" required value={draft.to} onChange={e => setDraft({ ...draft, to: e.target.value })} disabled={busy} /></label>
      <div className={styles.filterActions}>
        <Button type="submit" disabled={busy}>{busy ? "Wczytuję…" : "Pokaż"}</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={reset}>Ostatnie 30 dni</Button>
      </div>
    </form>

    <p role="status" className="result-count">
      {busy ? "Wczytuję statystyki…" : period ? `Okres: ${formatDay(period.from)} – ${formatDay(period.to)}` : ""}
    </p>
    <p role="alert" className="form-error">{error}</p>

    {stats && <div className={styles.grid} aria-busy={busy}>
      <Block id="site-title" title="Ruch w serwisie" lead="Odsłony stron i osoby, które odwiedziły serwis, zalogowane lub nie.">
        <dl className={styles.metrics}>
          <Metric label="Wizyty" value={stats.site.visits} />
          <Metric label="Unikalni odwiedzający" value={stats.site.unique_visitors} />
          <Metric label="Rozpoczęte rozmowy" value={stats.site.conversations} />
          <Metric label="Zarejestrowani użytkownicy (łącznie)" value={stats.site.registered_users} />
        </dl>
        {!stats.site.visits && !stats.site.conversations && <p className={styles.empty}>W tym okresie nie odnotowano wizyt ani rozmów.</p>}
        <Daily caption="Ruch w serwisie według dni" head={["Dzień", "Wizyty", "Odwiedzający", "Rozmowy"]}
          rows={stats.site.series.map(day => [formatDay(day.date), formatNumber(day.visits), formatNumber(day.unique_visitors), formatNumber(day.conversations)])} />
      </Block>

      <Block id="workspace-title" title="Czat na stronie głównej" lead="Rozmowy zalogowanych osób i wynik każdego wysłanego pytania.">
        <dl className={styles.metrics}>
          <Metric label="Rozpoczęte rozmowy" value={stats.workspace.threads} />
          <Metric label="Osoby" value={stats.workspace.unique_users} />
          <Metric label="Wysłane pytania" value={stats.workspace.operations} />
          <Metric label="Z dopasowaną innowacją" value={stats.workspace.outcomes.matched} />
          <Metric label="Bez dopasowania" value={stats.workspace.outcomes.no_match} />
          <Metric label="Baza wiedzy niedostępna" value={stats.workspace.outcomes.unavailable} />
        </dl>
        <p className={styles.lead}>Status pytań: zakończone {formatNumber(stats.workspace.completed)}, nieudane {formatNumber(stats.workspace.failed)}, w trakcie {formatNumber(stats.workspace.processing)}.</p>
        {!stats.workspace.operations && <p className={styles.empty}>W tym okresie nikt nie wysłał pytania w czacie.</p>}
        <Daily caption="Czat na stronie głównej według dni" head={["Dzień", "Rozmowy", "Pytania", "Dopasowane", "Bez dopasowania", "Niedostępne"]}
          rows={stats.workspace.series.map(day => [formatDay(day.date), formatNumber(day.threads), formatNumber(day.operations), formatNumber(day.matched), formatNumber(day.no_match), formatNumber(day.unavailable)])} />
      </Block>

      <Block id="topics-title" title="Tematy w czasie" lead={`Każdy punkt wykresu to liczba różnych osób, które pytały o temat w ${stats.timeline.window_days} dniach kończących się danego dnia${stats.timeline.step_days > 1 ? ` (punkt co ${stats.timeline.step_days} dni)` : ""}. Najczęściej wyszukiwane tematy są na górze. Zmiana porównuje wybrany okres z poprzednim okresem tej samej długości. „Bez odpowiedzi” to rozmowy, w których czat ostatecznie nie znalazł pasującej innowacji.`}>
        <TopicCharts timeline={stats.timeline} />
        {tagRows.length > 0 && <Disclosure summary="Tabela tematów i podtematów">
          <Table caption="Tematy rozmów w wybranym okresie" head={["Temat", "Rozmowy", "Osoby", "Bez odpowiedzi"]} rows={tagRows} />
        </Disclosure>}
        {stats.trends.items.length > 0 && <Disclosure summary="Tabela trendów">
          <Table caption="Trendy tematów" head={["Temat", "Wybrany okres", "Poprzedni okres", "Zmiana"]}
            rows={stats.trends.items.map(item => [
              item.subtag_name ? <span key="name">{item.tag_name} › {item.subtag_name}</span> : item.tag_name,
              formatNumber(item.current), formatNumber(item.previous), <TrendChange key="change" value={item.change} pct={item.change_pct} />,
            ])} />
        </Disclosure>}
      </Block>

      <Block id="innovations-title" title="Najczęściej proponowane innowacje" lead={`Innowacje z bazy wiedzy pokazane w czacie. „Wyświetlenia” to rozmowy, w których się pojawiły, „Otwarcia” – rozmowy, w których ktoś otworzył ich opis.${stats.innovations.total > stats.innovations.items.length ? ` Pokazano ${formatNumber(stats.innovations.items.length)} z ${formatNumber(stats.innovations.total)}.` : ""}`}>
        {stats.innovations.items.length ? <Table caption="Najczęściej proponowane innowacje" head={["Innowacja", "Osoby", "Wyświetlenia", "Otwarcia"]}
          rows={stats.innovations.items.map(item => [
            item.title, formatNumber(item.unique_searchers), formatNumber(item.times_shown), formatNumber(item.opened),
          ])} />
          : <p className={styles.empty}>W tym okresie czat nie zaproponował żadnej innowacji.</p>}
      </Block>
    </div>}
  </section>;
}
