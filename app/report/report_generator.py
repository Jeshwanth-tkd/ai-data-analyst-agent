"""
Phase 26: Report Generation.

Bundles analyze_csv_file()'s entire result dict -- insights, every chart,
data quality, the agent's plan, automatic EDA, anomalies, statistical
tests, cleaning suggestions, and forecast (whichever sections are
actually present) -- into ONE self-contained HTML file. Every chart
image is embedded directly as a base64 data: URI, not linked to a
separate file, so the report is a single portable file that opens
correctly anywhere (email attachment, USB drive, offline) with no
broken image links.

Design decision, made deliberately (not a default fallen into): HTML,
not PDF. PDF-via-pandoc+LaTeX and PDF-via-weasyprint were both
considered and rejected -- both need a heavy system dependency (a full
TeX Live install, or Cairo/Pango) that's slow and risky to add to
Streamlit Community Cloud's free-tier build environment. A
self-contained HTML file achieves the same practical goal (one
shareable file with everything embedded) without that deployment risk
-- and a user who wants a literal PDF can still print the HTML to one
from any browser.

This module never talks to the LLM and never re-runs any analysis -- it
only reads the already-computed result dict and already-saved chart
files (report generation itself is a formatting step, not a new report).
"""

import base64
import html
import os

REPORT_OUTPUT_PATH = os.path.join("outputs", "report.html")

_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 900px;
       margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }
h1 { border-bottom: 3px solid #4CAF50; padding-bottom: 0.5rem; }
h2 { color: #2c3e50; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; }
.report-section { margin-bottom: 1.5rem; }
.chart-grid { display: flex; flex-wrap: wrap; gap: 1rem; }
.chart-grid figure { margin: 0; max-width: 420px; }
.chart-grid img { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }
figcaption { font-size: 0.85rem; color: #666; margin-top: 0.25rem; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9rem; }
th { background: #f5f5f5; }
.error { color: #c0392b; }
footer { margin-top: 3rem; color: #999; font-size: 0.8rem; text-align: center; }
"""


def _embed_image(path: str) -> str:
    """Reads an image file off disk and returns it as a base64 data: URI."""
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _section(title: str, body_html: str) -> str:
    # Every render_* helper returns "" when it has nothing to show --
    # skip the whole <section> (including its <h2>) rather than
    # printing an empty, misleading heading.
    if not body_html:
        return ""
    return f'<section class="report-section"><h2>{html.escape(title)}</h2>{body_html}</section>'


def _render_charts(chart_paths: list) -> str:
    if not chart_paths:
        return ""
    figures = []
    for path in chart_paths:
        if not os.path.exists(path):
            continue
        name = html.escape(os.path.basename(path))
        figures.append(
            f'<figure><img src="{_embed_image(path)}" alt="{name}"><figcaption>{name}</figcaption></figure>'
        )
    return f'<div class="chart-grid">{"".join(figures)}</div>' if figures else ""


def _render_insights(insights: list) -> str:
    if not insights:
        return ""
    items = "".join(f"<li>{html.escape(i)}</li>" for i in insights)
    return f"<ul>{items}</ul>"


def _render_quality(quality: dict) -> str:
    scores = quality["scores"]
    rows = "".join(
        f"<tr><td>{html.escape(name.replace('_', ' ').title())}</td><td>{value}/100</td></tr>"
        for name, value in scores.items()
    )
    flags = quality["structural_flags"]
    flag_lines = []
    if flags["constant_columns"]:
        flag_lines.append(f"Constant columns: {html.escape(', '.join(flags['constant_columns']))}")
    if flags["id_like_columns"]:
        flag_lines.append(f"Identifier-like columns: {html.escape(', '.join(flags['id_like_columns']))}")
    if flags["high_cardinality_columns"]:
        flag_lines.append(f"High-cardinality columns: {html.escape(', '.join(flags['high_cardinality_columns']))}")
    flags_html = "".join(f"<li>{line}</li>" for line in flag_lines)
    flags_block = f"<ul>{flags_html}</ul>" if flags_html else ""
    return (
        f"<p><strong>Overall score: {quality['overall_score']}/100</strong></p>"
        f"<table><tbody>{rows}</tbody></table>{flags_block}"
    )


def _render_plan(plan: dict) -> str:
    steps = "".join(f"<li>{html.escape(step)}</li>" for step in plan.get("steps", []))
    return f"<p><strong>Goal:</strong> {html.escape(plan.get('goal', ''))}</p><ol>{steps}</ol>"


def _render_anomalies(anomalies: dict) -> str:
    parts = []
    iso = anomalies.get("isolation_forest", {})
    if iso.get("ran"):
        parts.append(
            f"<p><strong>Row-level anomalies (Isolation Forest):</strong> "
            f"{iso['anomalous_row_count']} of {iso['rows_checked']} rows flagged "
            f"({iso['anomalous_row_pct']}%).</p>"
        )
    z_outliers = anomalies.get("z_score_outliers", {})
    if z_outliers:
        items = "".join(
            f"<li>{html.escape(col)}: {info['outlier_count']} value(s) ({info['outlier_pct']}%) "
            f"more than 3 standard deviations from the mean</li>"
            for col, info in z_outliers.items()
        )
        parts.append(f"<p><strong>Per-column z-score outliers:</strong></p><ul>{items}</ul>")
    return "".join(parts)


def _render_statistical_tests(stats_report: dict) -> str:
    if not stats_report.get("top_significant_results"):
        return "<p>No statistically significant relationships found.</p>"
    rows = "".join(
        f"<tr><td>{html.escape(r['categorical_column'])}</td><td>{html.escape(r['numeric_column'])}</td>"
        f"<td>{html.escape(r['test'])}</td><td>{r['p_value']}</td></tr>"
        for r in stats_report["top_significant_results"]
    )
    note = html.escape(stats_report.get("multiple_comparisons_note", ""))
    return (
        f"<p>{stats_report['significant_results_count']} of {stats_report['total_tests_run']} tests significant.</p>"
        f"<table><thead><tr><th>Categorical</th><th>Numeric</th><th>Test</th><th>p-value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table><p><em>{note}</em></p>"
    )


def _render_cleaning(cleaning: dict) -> str:
    items = "".join(
        f"<li>{'✅ Auto-applied' if a['auto_applied'] else '💡 Suggested'}: {html.escape(a['description'])}</li>"
        for a in cleaning["suggestions"]
    )
    log_items = "".join(f"<li>{html.escape(line)}</li>" for line in cleaning.get("log", []))
    log_block = f"<p><strong>Changes actually made:</strong></p><ul>{log_items}</ul>" if log_items else ""
    return f"<ul>{items}</ul>{log_block}"


def _render_forecast(forecast: dict) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(p['date'])}</td><td>{p['predicted_value']}</td><td>{p['naive_baseline']}</td></tr>"
        for p in forecast["forecast"]
    )
    chart_html = _render_charts([forecast["chart_path"]])
    return (
        f"<p>Forecasting <strong>{html.escape(forecast['value_column'])}</strong> over "
        f"<strong>{html.escape(forecast['date_column'])}</strong>, based on "
        f"{forecast['historical_points']} historical points.</p>"
        f"{chart_html}"
        f"<table><thead><tr><th>Date</th><th>Predicted</th><th>Naive baseline</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def generate_html_report(result: dict, dataset_name: str = "dataset") -> str:
    """
    Builds the complete self-contained HTML report as a string. Every
    section is optional and only appears when the corresponding data is
    actually present in `result` -- this function works the same way on
    a fully successful run, a run where only the LLM step failed, or a
    run where ingestion itself failed (mirroring the "renders
    unconditionally" pattern already used throughout streamlit_app.py).
    """
    sections = []

    quality = result.get("data_quality")
    if quality:
        sections.append(_section("Data Health", _render_quality(quality)))

    plan = result.get("plan")
    if plan:
        sections.append(_section("Agent's Plan", _render_plan(plan)))

    if result.get("success"):
        sections.append(_section("Insights", _render_insights(result.get("insights", []))))
        sections.append(_section("Charts", _render_charts(result.get("charts", []))))
    elif result.get("error"):
        sections.append(_section("Analysis Status", f"<p class='error'>Analysis failed: {html.escape(str(result['error']))}</p>"))

    auto_charts = result.get("auto_eda_charts")
    if auto_charts:
        sections.append(_section("Automatic EDA", _render_charts(auto_charts)))

    anomalies = result.get("anomalies")
    if anomalies and (anomalies.get("isolation_forest", {}).get("ran") or anomalies.get("z_score_outliers")):
        sections.append(_section("Anomaly Detection", _render_anomalies(anomalies)))

    stats_report = result.get("statistical_tests")
    if stats_report and stats_report.get("total_tests_run"):
        sections.append(_section("Statistical Tests", _render_statistical_tests(stats_report)))

    cleaning = result.get("cleaning")
    if cleaning and cleaning.get("suggestions"):
        sections.append(_section("Cleaning Suggestions", _render_cleaning(cleaning)))

    forecast = result.get("forecast")
    if forecast and forecast.get("ran"):
        sections.append(_section("Forecast", _render_forecast(forecast)))

    body = "".join(sections) or "<p>No results to show for this file.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Data Analysis Report: {html.escape(dataset_name)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Data Analysis Report: {html.escape(dataset_name)}</h1>
{body}
<footer>Generated by the AI-Powered Data Analyst Agent.</footer>
</body>
</html>"""


def save_html_report(result: dict, dataset_name: str = "dataset", output_path: str = REPORT_OUTPUT_PATH) -> str:
    """Renders the report and writes it to disk, returning the path written."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    content = generate_html_report(result, dataset_name=dataset_name)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


# Demo block, same convention as every other module in this project:
#   python -m app.report.report_generator data/samples/sample_sales.csv
if __name__ == "__main__":
    import sys

    from app.output.insights import analyze_csv_file

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    result = analyze_csv_file(csv_path)
    dataset_name = os.path.basename(csv_path)
    path = save_html_report(result, dataset_name=dataset_name)
    print(f"Report saved to: {path}")
