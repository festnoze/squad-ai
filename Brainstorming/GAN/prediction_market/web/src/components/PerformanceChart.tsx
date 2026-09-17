import { useMemo, useState } from "react";
import { date, decimal } from "../util";
import { PriceChart } from "./PriceChart";

export interface PerformanceCurve { id: string; label: string; initial: number; points: { t: number; value: number }[] }
const colors = ["#187888", "#b76831", "#775bad", "#3f865b", "#b44365"];
export function PerformanceChart({ curves, currency, independent = false }: { curves: PerformanceCurve[]; currency: string; independent?: boolean }) {
  const [metric, setMetric] = useState<"return" | "capital" | "drawdown">("return");
  const [hidden, setHidden] = useState<string[]>([]);
  const [cursor, setCursor] = useState<number | undefined>();
  const prepared = useMemo(() => curves.map(curve => {
    let peak = curve.initial;
    const points = [...new Map(curve.points.map(point => [point.t, point])).values()].sort((a, b) => a.t - b.t);
    return { ...curve, points: points.map(point => { peak = Math.max(peak, point.value); return { ...point,
      display: metric === "capital" ? point.value / 100 : metric === "return" ? (point.value / curve.initial - 1) * 100 : (point.value / peak - 1) * 100 }; }) };
  }), [curves, metric]);
  const times = useMemo(() => [...new Set(prepared.flatMap(curve => curve.points.map(point => point.t)))].sort((a, b) => a - b), [prepared]);
  if (!times.length) return <p className="muted">Aucune courbe enregistrée pour cette période.</p>;
  const series = prepared.filter(curve => !hidden.includes(curve.id)).map(curve => {
    let index = 0;
    return { id: curve.id, label: curve.label, color: colors[curves.findIndex(row => row.id === curve.id) % colors.length], values: times.map(time => {
      while (index + 1 < curve.points.length && curve.points[index + 1].t <= time) index++;
      const point = curve.points[index];
      return !point || time < point.t || time > curve.points[curve.points.length - 1].t ? null : point.display;
    }) };
  });
  const equalCapital = curves.every(curve => curve.initial === curves[0].initial);
  if (metric !== "capital" || equalCapital) series.push({ id: "cash", label: "Sans transaction", color: "#86939a", values: times.map(() => metric === "capital" ? curves[0].initial / 100 : 0) });
  const active = Math.min(cursor ?? times.length - 1, times.length - 1);
  const unit = metric === "capital" ? currency.toUpperCase() : "%";
  return <section className="performance-chart" aria-label="Comparatif des agents dans le temps">
    <div className="chart-toolbar"><h3>Comparer les trajectoires</h3><label>Mesure<select aria-label="Mesure du graphique" value={metric} onChange={event => setMetric(event.target.value as typeof metric)}><option value="return">Rendement net (%)</option><option value="capital">Capital ({currency.toUpperCase()})</option><option value="drawdown">Repli depuis le sommet (%)</option></select></label></div>
    <p className="muted small">{metric === "return" ? "Écart au capital initial, frais inclus. 0 % correspond à conserver son capital sans transaction." : metric === "drawdown" ? "Distance au meilleur capital déjà atteint. Plus la courbe descend, plus la baisse est importante." : "Capital valorisé, y compris les positions encore ouvertes ; il ne s’agit pas uniquement de gains encaissés."} {independent ? "Finalistes évalués séparément sur la même période ; les capitaux ne s’additionnent pas." : "Agents de la même simulation, avec liquidité simulée partagée."}</p>
    <div className="curve-toggles">{curves.map((curve, index) => <label key={curve.id}><input type="checkbox" checked={!hidden.includes(curve.id)} onChange={() => setHidden(previous => previous.includes(curve.id) ? previous.filter(id => id !== curve.id) : [...previous, curve.id])} /><i style={{ background: colors[index % colors.length] }} />{curve.label}</label>)}</div>
    <PriceChart times={times} series={series} fixedDomain={false} cursor={active} onCursor={setCursor} title={`${metric === "drawdown" ? "Repli" : metric === "return" ? "Rendement net" : "Capital"} des agents en ${unit}`} />
    <label className="timeline-control">Examiner une date<input type="range" min="0" max={times.length - 1} value={active} onChange={event => setCursor(Number(event.target.value))} aria-valuetext={date(times[active], true)} /></label>
    <div className="chart-readout" aria-live="polite"><strong>{date(times[active], true)} UTC</strong>{series.map(row => <span key={row.id}>{row.label} : <b>{row.values[active] === null ? "indisponible" : `${decimal(row.values[active]!, 2)} ${unit}`}</b></span>)}</div>
  </section>;
}
