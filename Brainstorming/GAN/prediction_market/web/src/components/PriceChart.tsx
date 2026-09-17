import { date, decimal } from "../util";

export interface ChartSeries { id: string; label: string; color: string; values: (number | null)[] }
export function PriceChart({ times, series, volumes, cursor, onCursor, title = "Prix et probabilités", fixedDomain = true, markers = [] }: {
  times: number[]; series: ChartSeries[]; volumes?: number[]; cursor?: number;
  onCursor?: (index: number) => void; title?: string; fixedDomain?: boolean; markers?: number[];
}) {
  if (!times.length) return <div className="empty compact">Aucun point disponible pour ce graphique.</div>;
  const width = 900, height = volumes ? 310 : 260, left = 52, right = 20, top = 18, bottom = volumes ? 84 : 34;
  const values = series.flatMap(s => s.values.filter((v): v is number => v !== null && Number.isFinite(v)));
  const minimum = fixedDomain || !values.length ? 0 : Math.min(...values);
  const maximum = fixedDomain ? 100 : !values.length ? 1 : Math.max(...values);
  const margin = fixedDomain ? 0 : Math.max((maximum - minimum) * .12, 1);
  const lo = minimum - margin, hi = maximum + margin;
  const x = (i: number) => left + (times[i] - times[0]) / Math.max(1, times[times.length - 1] - times[0]) * (width - left - right);
  const y = (value: number) => top + (hi - value) / Math.max(hi - lo, 1) * (height - top - bottom);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + (hi - lo) * i / 4);
  const volumeMax = Math.max(1, ...(volumes ?? []));
  const active = cursor ?? times.length - 1;
  const path = (values: (number | null)[]) => {
    let previous = false;
    return values.map((value, i) => {
      if (value === null || !Number.isFinite(value)) { previous = false; return ""; }
      const point = `${previous ? "L" : "M"}${x(i).toFixed(2)},${y(value).toFixed(2)}`;
      previous = true;
      return point;
    }).join(" ");
  };
  return <div className="chart-wrap">
    <div className="chart-legend">{series.map(s => <span key={s.id}><i style={{ background: s.color }} />{s.label}</span>)}{volumes && <span><i className="volume-key" />Volume</span>}</div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} className={onCursor ? "chart interactive" : "chart"}
      onPointerDown={event => {
        if (!onCursor) return;
        const rect = event.currentTarget.getBoundingClientRect();
        const point = (event.clientX - rect.left) / rect.width * width;
        const target = times[0] + (point - left) / (width - left - right) * (times[times.length - 1] - times[0]);
        onCursor(times.reduce((best, time, index) => Math.abs(time - target) < Math.abs(times[best] - target) ? index : best, 0));
      }}>
      <title>{title}</title>
      {ticks.map((tick, i) => <g key={i}><line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} className="grid-line" /><text x={left - 10} y={y(tick) + 4} textAnchor="end" className="axis-label">{decimal(tick, fixedDomain ? 0 : 1)}{fixedDomain ? "%" : ""}</text></g>)}
      {volumes?.map((volume, i) => <rect key={i} x={x(i) - Math.min(6, (width - left - right) / times.length * .35)} y={height - 33 - volume / volumeMax * 36} width={Math.max(1, Math.min(12, (width - left - right) / times.length * .7))} height={volume / volumeMax * 36} className="volume-bar" />)}
      {series.map(s => <path key={s.id} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.id === "market" ? 2.8 : 2} strokeLinejoin="round" strokeLinecap="round" />)}
      {times.length <= 3 && series.map(s => s.values.map((value, index) => value !== null && Number.isFinite(value) && <circle key={`${s.id}-${index}`} cx={x(index)} cy={y(value)} r="4" fill={s.color} />))}
      {markers.map((index, i) => <circle key={i} cx={x(index)} cy={height - bottom + 7} r="3" fill="#b16b2d"><title>Exécution simulée le {date(times[index])}</title></circle>)}
      {cursor !== undefined && <g><line x1={x(active)} x2={x(active)} y1={top} y2={height - 30} className="cursor-line" />{series.map(s => s.values[active] !== null && s.values[active] !== undefined && <circle key={s.id} cx={x(active)} cy={y(s.values[active]!)} r="4" fill={s.color} stroke="white" strokeWidth="2" />)}</g>}
      <text x={left} y={height - 8} className="axis-label">{date(times[0])}</text>
      <text x={width - right} y={height - 8} textAnchor="end" className="axis-label">{date(times[times.length - 1])}</text>
    </svg>
  </div>;
}
