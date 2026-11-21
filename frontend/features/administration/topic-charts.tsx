import type { TagTimeline } from "./api";
import styles from "./administration.module.css";

const width = 300;
const height = 72;
const pad = 4;

function shortDay(day: string) { return new Date(`${day}T00:00:00Z`).toLocaleDateString("pl-PL", { timeZone: "UTC", day: "numeric", month: "numeric" }); }
function longDay(day: string) { return new Date(`${day}T00:00:00Z`).toLocaleDateString("pl-PL", { timeZone: "UTC" }); }
export function people(count: number) {
  const tens = count % 100, ones = count % 10;
  const word = count === 1 ? "osoba" : ones >= 2 && ones <= 4 && (tens < 12 || tens > 14) ? "osoby" : "osób";
  return `${count.toLocaleString("pl-PL")} ${word}`;
}
function change(value: number, pct: number | null) {
  const sign = value > 0 ? "+" : "";
  const count = value.toLocaleString("pl-PL");
  return pct === null ? `${sign}${count}` : `${sign}${count} (${sign}${pct.toLocaleString("pl-PL")}%)`;
}

const trends = {
  up: { arrow: "▲", text: "wzrost", className: styles.trendUp },
  down: { arrow: "▼", text: "spadek", className: styles.trendDown },
  flat: { arrow: "=", text: "bez zmian", className: styles.trendFlat },
};

/** Signed change with a direction arrow, colour and screen-reader text; colour is never the only cue. */
export function TrendChange({ value, pct, context }: { value: number; pct: number | null; context?: string }) {
  const trend = trends[value > 0 ? "up" : value < 0 ? "down" : "flat"];
  return <span className={`${styles.topicChange} ${trend.className}`}>
    <span aria-hidden="true">{trend.arrow} </span><span className="sr-only">{trend.text}: </span>{change(value, pct)}
    {context && <span className="sr-only"> {context}</span>}
  </span>;
}

function linePath(points: number[], from: number, to: number, x: (i: number) => number, y: (v: number) => number) {
  // A single-point segment (one-day period) is drawn as a short tick so it stays visible.
  if (to - from === 1) return `M${x(from) - 3},${y(points[from])}H${x(from) + 3}`;
  let path = "";
  for (let i = from; i < to; i++) path += `${i === from ? "M" : "L"}${x(i)},${y(points[i])}`;
  return path;
}

function Chart({ timeline, item, max }: { timeline: TagTimeline; item: TagTimeline["items"][number]; max: number }) {
  const { dates } = timeline;
  const split = dates.findIndex(point => point.current);
  const last = dates.length - 1;
  const x = (i: number) => (last ? (i / last) * width : width / 2);
  const y = (v: number) => height - pad - (v / max) * (height - 2 * pad);
  const current = linePath(item.points, split, dates.length, x, y);
  const peak = item.points.reduce((best, value, i) => value > item.points[best] ? i : best, split);
  const span = `w ${timeline.window_days} dniach do`;
  const label = `${item.name}: ${people(item.unique_people)} w wybranym okresie, ${people(item.previous_people)} w poprzednim. `
    + (item.points[peak] ? `Najwięcej w wybranym okresie: ${people(item.points[peak])} ${span} ${longDay(dates[peak].date)}.` : "Brak pytań w wybranym okresie.");
  const step = last ? width / last : width;
  return <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
    <line x1={0} x2={width} y1={height - pad} y2={height - pad} className={styles.chartBase} vectorEffect="non-scaling-stroke" />
    <line x1={(x(split - 1) + x(split)) / 2} x2={(x(split - 1) + x(split)) / 2} y1={0} y2={height} className={styles.chartSplit} vectorEffect="non-scaling-stroke" />
    <path d={linePath(item.points, 0, split, x, y)} className={styles.chartPrevious} vectorEffect="non-scaling-stroke" />
    {dates.length - split > 1 && <path d={`${current}V${height - pad}H${x(split)}Z`} className={styles.chartArea} />}
    <path d={current} className={styles.chartCurrent} vectorEffect="non-scaling-stroke" />
    {dates.map((point, i) => <rect key={point.date} x={x(i) - step / 2} width={step} y={0} height={height} className={styles.chartHit}>
      <title>{`${people(item.points[i])} ${span} ${longDay(point.date)}`}</title>
    </rect>)}
  </svg>;
}

export function TopicCharts({ timeline }: { timeline: TagTimeline }) {
  const active = timeline.items.filter(item => item.unique_people || item.previous_people);
  const idle = timeline.items.filter(item => !item.unique_people && !item.previous_people);
  const max = Math.max(1, ...active.flatMap(item => item.points));
  const split = timeline.dates.findIndex(point => point.current);
  const splitPct = timeline.dates.length > 1 ? ((split - 0.5) / (timeline.dates.length - 1)) * 100 : 50;

  if (!timeline.items.length) return <p className={styles.empty}>Nie zdefiniowano jeszcze tematów.</p>;
  return <>
    <ul className={styles.legend} aria-label="Legenda wykresów">
      <li><span className={styles.swatchPrevious} aria-hidden="true" />Poprzedni okres ({longDay(timeline.previous_period.from)} – {longDay(timeline.previous_period.to)})</li>
      <li><span className={styles.swatchCurrent} aria-hidden="true" />Wybrany okres ({longDay(timeline.period.from)} – {longDay(timeline.period.to)})</li>
      <li>Wspólna skala 0–{max}</li>
    </ul>
    {active.length ? <ul className={styles.topicGrid}>{active.map(item => <li key={item.tag_id} className={styles.topicCard}>
      <h3>{item.name}</h3>
      <p className={styles.topicFigure}>
        <strong>{people(item.unique_people)}</strong>
        <TrendChange value={item.change} pct={item.change_pct} context="względem poprzedniego okresu" />
      </p>
      <p className={styles.topicMeta}>Rozmowy: {item.conversations.toLocaleString("pl-PL")} · bez odpowiedzi: {item.no_answer.toLocaleString("pl-PL")} · poprzednio: {people(item.previous_people)}</p>
      <Chart timeline={timeline} item={item} max={max} />
      <div className={styles.axis} aria-hidden="true">
        <span style={{ left: 0 }}>{shortDay(timeline.dates[0].date)}</span>
        <span style={{ left: `${splitPct}%`, transform: "translateX(-50%)" }}>{shortDay(timeline.period.from)}</span>
        <span style={{ right: 0 }}>{shortDay(timeline.period.to)}</span>
      </div>
    </li>)}</ul> : <p className={styles.empty}>Brak rozmów z przypisanym tematem w obu okresach.</p>}
    {active.length > 0 && idle.length > 0 && <p className={styles.empty}>Bez pytań w obu okresach: {idle.map(item => item.name).join(", ")}.</p>}
  </>;
}
