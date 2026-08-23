"""Self-contained HTML report with inline SVG charts. No dependencies."""

import json

COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
          "#59a14f", "#edc948", "#b07aa1", "#9c755f"]


def _line_chart(title, series, width=880, height=300):
    """series: list of (label, [floats]). Returns an HTML section string."""
    all_values = [v for _, values in series for v in values]
    if not all_values:
        return ""
    vmin, vmax = min(all_values), max(all_values)
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0
    pad = 46
    n = max(len(values) for _, values in series)

    def sx(i):
        return pad + i * (width - 2 * pad) / max(1, n - 1)

    def sy(v):
        return height - pad - (v - vmin) * (height - 2 * pad) / (vmax - vmin)

    parts = [f'<svg viewBox="0 0 {width} {height}" '
             f'style="width:100%;height:auto;background:#fff;border:1px solid #ddd;border-radius:8px">']
    parts.append(f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" '
                 f'y2="{height - pad}" stroke="#999"/>')
    parts.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" '
                 f'y2="{height - pad}" stroke="#999"/>')
    parts.append(f'<text x="{pad - 6}" y="{sy(vmax) + 4}" text-anchor="end" '
                 f'font-size="11" fill="#666">{vmax:,.1f}</text>')
    parts.append(f'<text x="{pad - 6}" y="{sy(vmin) + 4}" text-anchor="end" '
                 f'font-size="11" fill="#666">{vmin:,.1f}</text>')
    parts.append(f'<text x="{width - pad}" y="{height - pad + 16}" text-anchor="end" '
                 f'font-size="11" fill="#666">gen {n - 1}</text>')
    for idx, (label, values) in enumerate(series):
        color = COLORS[idx % len(COLORS)]
        points = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(values))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" '
                     f'points="{points}"><title>{label}</title></polyline>')
    parts.append("</svg>")

    legend = "".join(
        f'<span style="margin-right:14px;font-size:13px">'
        f'<span style="display:inline-block;width:10px;height:10px;'
        f'background:{COLORS[i % len(COLORS)]};border-radius:2px;'
        f'margin-right:4px"></span>{label}</span>'
        for i, (label, _) in enumerate(series))

    return (f'<section style="margin:24px 0"><h2 style="font-size:17px">{title}</h2>'
            f'{"".join(parts)}<div style="margin-top:6px">{legend}</div></section>')


def render_report(config, history, leaderboard):
    gens = [row["generation"] for row in history]
    wealth_chart = _line_chart("Wealth over generations", [
        ("max", [row["max_wealth"] for row in history]),
        ("mean", [row["mean_wealth"] for row in history]),
        ("median", [row["median_wealth"] for row in history]),
    ])
    turnover_chart = _line_chart("Deaths and immigration per generation", [
        ("deaths", [float(row["deaths"]) for row in history]),
        ("immigrants", [float(row["immigrants"]) for row in history]),
    ])
    gene_names = list(history[0]["gene_means"].keys()) if history else []
    gene_chart = _line_chart("Population gene means (selection at work)", [
        (name, [row["gene_means"][name] for row in history])
        for name in gene_names
    ])

    gene_cols = "".join(f"<th>{name}</th>" for name in gene_names)
    rows = []
    for rank, entry in enumerate(leaderboard, start=1):
        genes = "".join(f"<td>{entry['genes'][name]:.2f}</td>" for name in gene_names)
        parents = ", ".join(str(p) for p in entry["parents"]) or "founder/immigrant"
        rows.append(
            f"<tr><td>{rank}</td><td>#{entry['id']}</td>"
            f"<td>{entry['wealth']:,.0f}</td><td>{entry['lifetime_pnl']:,.0f}</td>"
            f"<td>{entry['born']}</td><td>{entry['age']}</td>"
            f"<td>{parents}</td>{genes}</tr>")
    table = (
        '<section style="margin:24px 0"><h2 style="font-size:17px">Final leaderboard</h2>'
        '<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:13px;width:100%">'
        "<thead><tr><th>#</th><th>agent</th><th>wealth</th><th>pnl</th>"
        f"<th>born</th><th>age</th><th>parents</th>{gene_cols}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>")

    last = history[-1] if history else {}
    header = (
        f"<h1 style='font-size:22px'>Money race report</h1>"
        f"<p style='color:#555'>{len(gens)} generations, population "
        f"{config.population}, seed {config.seed}, arenas: "
        f"{', '.join(config.arenas)}.</p>"
        f"<p>Final economy: total wealth {last.get('total_wealth', 0):,.0f}, "
        f"richest agent {last.get('max_wealth', 0):,.0f}, "
        f"{sum(row['deaths'] for row in history)} deaths overall.</p>")

    config_block = (f"<details><summary style='cursor:pointer'>Run config</summary>"
                    f"<pre style='background:#f6f6f6;padding:10px;border-radius:6px'>"
                    f"{json.dumps(config.as_dict(), indent=2)}</pre></details>")

    style = ("<style>body{font-family:Segoe UI,system-ui,sans-serif;max-width:960px;"
             "margin:32px auto;padding:0 16px;color:#222;background:#fafafa}"
             "th,td{border:1px solid #ddd;padding:4px 8px;text-align:right}"
             "th{background:#eee}td:nth-child(2),td:nth-child(7){text-align:left}</style>")

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Money race report</title>" + style + "</head><body>"
            + header + wealth_chart + gene_chart + turnover_chart + table
            + config_block + "</body></html>")
