import Plot from "react-plotly.js";
import type { TimeSeriesPoint } from "../types";

interface PortfolioChartProps {
  portfolioValues: TimeSeriesPoint[];
  buyHoldValues: TimeSeriesPoint[];
  title?: string;
}

export default function PortfolioChart({
  portfolioValues,
  buyHoldValues,
  title = "Portfolio vs Buy & Hold",
}: PortfolioChartProps) {
  return (
    <Plot
      data={[
        {
          x: portfolioValues.map((p) => p.date),
          y: portfolioValues.map((p) => p.value),
          type: "scatter",
          mode: "lines",
          name: "Strategy",
          line: { color: "#a855f7", width: 2 },
        },
        {
          x: buyHoldValues.map((p) => p.date),
          y: buyHoldValues.map((p) => p.value),
          type: "scatter",
          mode: "lines",
          name: "Buy & Hold",
          line: { color: "#64748b", width: 1.5, dash: "dot" },
        },
      ]}
      layout={{
        title: { text: title, font: { color: "#e2e8f0", size: 14 } },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#94a3b8" },
        xaxis: { gridcolor: "#334155", linecolor: "#334155" },
        yaxis: {
          gridcolor: "#334155",
          linecolor: "#334155",
          tickprefix: "$",
        },
        legend: { orientation: "h", y: -0.15 },
        margin: { t: 40, r: 20, b: 50, l: 70 },
        autosize: true,
      }}
      useResizeHandler
      className="w-full"
      style={{ width: "100%", height: "320px" }}
    />
  );
}
