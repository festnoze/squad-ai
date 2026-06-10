import Plot from "react-plotly.js";
import type { TimeSeriesPoint } from "../types";

interface PriceChartProps {
  prices: TimeSeriesPoint[];
  entries: string[];
  exits: string[];
  title?: string;
}

export default function PriceChart({
  prices,
  entries,
  exits,
  title = "Price",
}: PriceChartProps) {
  const dates = prices.map((p) => p.date);
  const values = prices.map((p) => p.value);

  const entryPrices = entries.map((d) => {
    const point = prices.find((p) => p.date === d);
    return point?.value ?? null;
  });

  const exitPrices = exits.map((d) => {
    const point = prices.find((p) => p.date === d);
    return point?.value ?? null;
  });

  return (
    <Plot
      data={[
        {
          x: dates,
          y: values,
          type: "scatter",
          mode: "lines",
          name: "Price",
          line: { color: "#94a3b8", width: 1.5 },
        },
        {
          x: entries,
          y: entryPrices,
          type: "scatter",
          mode: "markers",
          name: "Buy",
          marker: { color: "#22c55e", size: 8, symbol: "triangle-up" },
        },
        {
          x: exits,
          y: exitPrices,
          type: "scatter",
          mode: "markers",
          name: "Sell",
          marker: { color: "#ef4444", size: 8, symbol: "triangle-down" },
        },
      ]}
      layout={{
        title: { text: title, font: { color: "#e2e8f0", size: 14 } },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#94a3b8" },
        xaxis: { gridcolor: "#334155", linecolor: "#334155" },
        yaxis: { gridcolor: "#334155", linecolor: "#334155" },
        legend: { orientation: "h", y: -0.15 },
        margin: { t: 40, r: 20, b: 50, l: 60 },
        autosize: true,
      }}
      useResizeHandler
      className="w-full"
      style={{ width: "100%", height: "320px" }}
    />
  );
}
