"""
Phase 8: Frontend.
Phase 10 pivot: this file used to talk to a separately-hosted FastAPI
backend over HTTP (`requests.post(...)`). It now calls the agent
pipeline directly, in the same process, by importing
`analyze_csv_file()` from app/output/insights.py.

Why the change: Phase 10 needed a genuinely free, no-credit-card,
persistent host for the FastAPI backend as a *second* service alongside
Streamlit. Hugging Face Spaces turned out to require a paid plan for
Docker Spaces (discovered live, contradicting earlier research), and
Vercel -- while free -- runs FastAPI as stateless serverless functions,
which is incompatible with our chart-serving design (one request saves
a chart file, a second request fetches it -- they could land on
different ephemeral containers with no shared disk). Running everything
as a single Streamlit app sidesteps both problems: there's only one
process, one filesystem, and one free host (Streamlit Community Cloud).

The tradeoff: this file now has direct knowledge of the agent's
internals (it imports from `app.*`), so it's no longer a thin,
swappable frontend the way it was talking to a backend over HTTP. For a
solo portfolio project favoring "actually deployed and free" over
"perfectly decoupled services," that's a reasonable trade -- and it's
worth being able to explain *why* in an interview.

Phase 17/18 additions: renders the agent's plan (goal + steps) and a
deterministic, LLM-independent "Automatic EDA" chart set, both attached
to analyze_csv_file()'s result dict.

Phase 19 addition: a chat section below the main result, backed by
app.agent.chat_agent.answer_data_question(). The uploaded file's raw
bytes (not the temp path, which gets deleted right after the main
analysis) are kept in session_state so each chat question can rebuild
its own temp CSV file on demand.

Phase 20/21 additions: renders the Phase 20 anomaly report (z-score
outliers + Isolation Forest row-level anomalies) and the Phase 21
hypothesis-test results, both attached to analyze_csv_file()'s result
dict, same "render unconditionally, independent of success/failure"
pattern as Data Health.

Phase 22 addition: a separate "SQL Analyst" section, reusing the same
retained uploaded_bytes as the chat section, backed by
app.sql.sql_analyst.answer_sql_question() -- a distinct alternate way to
query the same dataset, with its own read-only-database safety model
(see that module's docstring) rather than reusing the pandas-code path.

Phase 23 addition: the file uploader now accepts Excel/JSON/Parquet
alongside CSV (app.ingestion.csv_profiler.load_data_file() dispatches by
extension). The original upload's extension is kept in session_state
alongside its raw bytes, so the chat and SQL Analyst sections -- which
each rebuild their own temp file from those bytes -- give the rebuilt
file the same suffix as the original upload rather than assuming ".csv".

Phase 24 addition: a "Cleaning Suggestions" section rendered from
analyze_csv_file()'s new "cleaning" key -- shows every suggested action
(auto-applied ones and manual-review-only ones distinguished visually),
the plain-language log of what was actually changed, and a download
button for the cleaned CSV when anything was auto-applied.

Phase 25 addition: a "Forecast" section, shown only when
analyze_csv_file()'s new "forecast" key actually ran (most datasets
aren't time series, so a not-ran forecast is the common case and isn't
surfaced as an error) -- the forecast chart plus a table of predicted
values against a naive last-value baseline.

Phase 26 addition: a "Download full report (HTML)" button, reading the
single self-contained HTML file analyze_csv_file() already generated at
result["report_path"] (app.report.report_generator) -- bundles every
section above into one portable, offline-viewable file.

Phase 27 addition: a UI/UX polish pass -- global CSS (a nicer font,
refined color accents, styled buttons/expanders/metrics), a consistent
icon per section, and app.ui.chart_carousel.render_chart_carousel()
replacing every plain vertical stack of st.image() calls with a
left/right-navigable, click-to-zoom carousel (Charts, Automatic EDA,
Forecast, and each chat reply's chart).
"""

import os
import tempfile

import pandas as pd
import streamlit as st

from app.agent.chat_agent import answer_data_question
from app.ingestion.csv_profiler import load_data_file, profile_dataframe
from app.output.insights import analyze_csv_file
from app.sql.sql_analyst import answer_sql_question
from app.ui.chart_carousel import render_chart_carousel

st.set_page_config(page_title="AI Data Analyst Agent", page_icon="📊", layout="centered")

# Phase 27: a single global stylesheet -- a cleaner font (Inter, with a
# system-font fallback stack so the app still looks fine offline or if
# the Google Fonts request is blocked), refined button/expander/metric
# styling, and a bit more breathing room. Kept as one small, inline
# st.markdown() block rather than a separate CSS file or a UI-theming
# package -- Streamlit has no built-in way to load an external
# stylesheet file, and this is little enough CSS that a dependency
# would be overkill for it.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', -apple-system, "Segoe UI", Roboto, sans-serif; }

    h1 { font-weight: 700; letter-spacing: -0.02em; }
    h2, h3 { font-weight: 600; }

    /* Buttons: rounded, subtle shadow, a single accent color used
       consistently everywhere a primary action appears. */
    .stButton > button, .stDownloadButton > button {
        border-radius: 8px;
        border: 1px solid #d7dbe0;
        font-weight: 500;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: #4C8BF5;
        box-shadow: 0 0 0 1px #4C8BF5;
        color: #4C8BF5;
    }

    /* Expanders: card-like, so each report section reads as a distinct
       block instead of blending into the page. No background color is
       set here on purpose -- an earlier version hardcoded a light
       background (#fafbfc), which clashed with Streamlit's dark theme
       (light text on a near-white box) and made text unreadable. A
       CSS-variable version was tried next (var(--secondary-background-color)),
       but this Streamlit version doesn't actually expose that as a
       global custom property, so it silently fell back to the same
       broken light color. Leaving background unset lets Streamlit's
       own theme-aware expander background show through correctly in
       both light and dark mode; only the border is styled here, using
       a semi-transparent gray that reads fine against either theme. */
    div[data-testid="stExpander"] {
        border: 1px solid rgba(128, 128, 128, 0.35);
        border-radius: 10px;
    }

    /* Metrics (Data Health scores): tighter, bolder numbers. */
    div[data-testid="stMetricValue"] { font-weight: 700; }

    /* Chat bubbles: a touch more rounding + spacing for readability. */
    div[data-testid="stChatMessage"] { border-radius: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 AI-Powered Data Analyst Agent")
st.write(
    "Upload a CSV, Excel, JSON, or Parquet file and an AI agent will "
    "write, run, and self-correct its own Python analysis code against "
    "it -- no manual EDA required."
)

# Phase 23: accept any format load_data_file() supports, not just CSV.
uploaded_file = st.file_uploader(
    "📁 Choose a data file", type=["csv", "xlsx", "xls", "json", "parquet"]
)

# st.button() only returns True on the exact rerun where it was clicked.
# Streamlit reruns this whole script on every interaction, so without
# this button as a deliberate trigger, we'd risk re-calling the LLM on
# every unrelated widget interaction -- wasteful and slow.
if uploaded_file is not None and st.button("🚀 Analyze"):
    with st.spinner(
        "Agent is thinking -- profiling your data, writing analysis code, "
        "running it, and self-correcting if it fails. This can take "
        "10-30 seconds..."
    ):
        # analyze_csv_file() needs a real file path on disk (it calls
        # load_data_file() -> pandas), but Streamlit only gives us the
        # uploaded bytes in memory. So we write those bytes out to a temp
        # file first, point the agent at that path, and clean the temp
        # file up afterwards -- the same handoff the FastAPI endpoint
        # used to do with UploadFile, just without the HTTP hop.
        # Phase 23: the temp file's suffix must match the ORIGINAL
        # upload's extension (not always ".csv") so load_data_file()
        # dispatches to the right parser -- an .xlsx's bytes written to a
        # ".csv"-suffixed file would be handed to the CSV parser and fail.
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=file_extension, delete=False
        ) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            result = analyze_csv_file(tmp_path)
            # Stored in session_state so the result survives future
            # reruns (e.g. if the user interacts with something else on
            # the page) without needing to re-run the whole analysis.
            st.session_state["result"] = result
            # Phase 19: keep the raw bytes around (not the temp path
            # itself, which we're about to delete) so the chat/SQL
            # sections below can write a fresh temp file per question.
            # Phase 23: the extension is kept alongside the bytes so
            # those rebuilt temp files also get the right suffix.
            # Starting a new analysis always resets the chat history --
            # old Q&A about a different dataset shouldn't linger.
            st.session_state["uploaded_bytes"] = uploaded_file.getvalue()
            st.session_state["uploaded_file_extension"] = file_extension
            st.session_state["chat_history"] = []
        finally:
            os.remove(tmp_path)

# Render whatever the most recent result was, on every rerun -- this is
# what makes the result stick around even after the button click itself
# has passed.
if "result" in st.session_state:
    result = st.session_state["result"]

    # Phase 12: the data quality report is attached to the result dict
    # regardless of whether the LLM/execution side succeeded, so this
    # renders unconditionally -- "here's what we know about your data"
    # is useful even on a failed analysis run.
    quality = result.get("data_quality")
    if quality:
        st.subheader("🩺 Data Health")

        score = quality["overall_score"]
        # A simple three-tier color signal (no extra charting library
        # needed) so "good vs. needs attention" is legible at a glance.
        badge = "🟢" if score >= 85 else "🟡" if score >= 60 else "🔴"
        st.metric("Overall score", f"{badge} {score}/100")

        sub_scores = quality["scores"]
        cols = st.columns(4)
        cols[0].metric("Missing values", f"{sub_scores['missing_values']}/100")
        cols[1].metric("Duplicates", f"{sub_scores['duplicates']}/100")
        cols[2].metric("Type consistency", f"{sub_scores['type_consistency']}/100")
        cols[3].metric("Outliers", f"{sub_scores['outliers']}/100")

        flags = quality["structural_flags"]
        flag_notes = []
        if flags["constant_columns"]:
            flag_notes.append(f"Constant columns (only one distinct value): {', '.join(flags['constant_columns'])}")
        if flags["id_like_columns"]:
            flag_notes.append(f"Identifier-like columns (almost all unique values): {', '.join(flags['id_like_columns'])}")
        if flags["high_cardinality_columns"]:
            flag_notes.append(f"High-cardinality columns (many distinct categories): {', '.join(flags['high_cardinality_columns'])}")
        if flags["inconsistent_categories"]:
            flag_notes.append(
                f"Possible inconsistent category spellings in: {', '.join(flags['inconsistent_categories'].keys())}"
            )

        if flag_notes:
            with st.expander("Structural notes"):
                for note in flag_notes:
                    st.write(f"- {note}")

    # Phase 17: show the plan the agent decided on before it wrote any
    # code. plan is None if planning itself failed (e.g. malformed LLM
    # response) -- code generation still works fine without it, so this
    # section just doesn't render rather than showing an error.
    plan = result.get("plan")
    if plan:
        st.subheader("🧭 Agent's Plan")
        st.write(f"**Goal:** {plan['goal']}")
        for i, step in enumerate(plan["steps"], start=1):
            st.write(f"{i}. {step}")

    # Phase 18: deterministic EDA charts, independent of the LLM run --
    # shown regardless of success/failure below, same reasoning as Data
    # Health above.
    auto_charts = result.get("auto_eda_charts")
    if auto_charts:
        with st.expander(f"📊 Automatic EDA ({len(auto_charts)} charts, no LLM involved)"):
            render_chart_carousel(auto_charts)

    # Phase 20: anomaly detection -- per-column z-score outliers and
    # row-level multivariate anomalies (Isolation Forest).
    anomalies = result.get("anomalies")
    if anomalies:
        iso = anomalies.get("isolation_forest", {})
        z_outliers = anomalies.get("z_score_outliers", {})
        if iso.get("ran") or z_outliers:
            with st.expander("🚨 Anomaly Detection"):
                if iso.get("ran"):
                    st.write(
                        f"**Row-level anomalies (Isolation Forest):** "
                        f"{iso['anomalous_row_count']} of {iso['rows_checked']} rows "
                        f"flagged ({iso['anomalous_row_pct']}%)"
                    )
                    if iso["top_anomalous_rows"]:
                        st.write("Most anomalous rows:")
                        st.table(iso["top_anomalous_rows"])
                elif iso.get("reason"):
                    st.caption(f"Row-level anomaly detection skipped: {iso['reason']}")

                if z_outliers:
                    st.write("**Per-column z-score outliers:**")
                    for col, info in z_outliers.items():
                        st.write(f"- {col}: {info['outlier_count']} values ({info['outlier_pct']}%) more than 3 standard deviations from the mean")

    # Phase 24: data cleaning agent -- deterministic suggestions plus
    # whatever conservative subset was auto-applied (never column drops,
    # see app/cleaning/data_cleaning.py's docstring). Rendered regardless
    # of success/failure below, same reasoning as Data Health.
    cleaning = result.get("cleaning")
    if cleaning and cleaning["suggestions"]:
        with st.expander(f"🧹 Cleaning Suggestions ({len(cleaning['suggestions'])})"):
            for action in cleaning["suggestions"]:
                if action["auto_applied"]:
                    st.write(f"✅ **Auto-applied:** {action['description']}")
                else:
                    st.write(f"💡 **Suggested (not applied):** {action['description']}")

            if cleaning["log"]:
                st.write("**What was actually changed:**")
                for line in cleaning["log"]:
                    st.write(f"- {line}")

            if cleaning["cleaned_csv_path"]:
                with open(cleaning["cleaned_csv_path"], "rb") as f:
                    st.download_button(
                        "⬇️ Download cleaned CSV",
                        data=f.read(),
                        file_name="cleaned_data.csv",
                        mime="text/csv",
                    )

    # Phase 25: forecasting -- only rendered when a usable date+numeric
    # pair was actually found (most datasets in this project aren't time
    # series at all, so "not ran" is the common, expected case, not an
    # error worth surfacing as one).
    forecast = result.get("forecast")
    if forecast and forecast.get("ran"):
        with st.expander(f"📈 Forecast: {forecast['value_column']} (next {forecast['forecast_periods']} periods)"):
            st.caption(
                f"Based on {forecast['historical_points']} historical points in "
                f"'{forecast['date_column']}'. Uses a simple trend model (Holt's linear "
                f"trend) -- doesn't account for seasonality. A naive baseline (repeating "
                f"the last observed value) is shown alongside it so you can judge whether "
                f"the trend model is actually adding anything."
            )
            render_chart_carousel([forecast["chart_path"]])
            st.table(forecast["forecast"])

    # Phase 21: automatic hypothesis tests between categorical and
    # numeric columns.
    stats_report = result.get("statistical_tests")
    if stats_report and stats_report["total_tests_run"] > 0:
        with st.expander(f"🧪 Statistical Tests ({stats_report['significant_results_count']} of {stats_report['total_tests_run']} significant)"):
            if stats_report["top_significant_results"]:
                for r in stats_report["top_significant_results"]:
                    st.write(
                        f"**{r['categorical_column']} vs {r['numeric_column']}** "
                        f"({r['test']}, p={r['p_value']}): group means {r['group_means']}"
                    )
            else:
                st.write("No statistically significant relationships found.")
            st.caption(stats_report["multiple_comparisons_note"])

    if result["success"]:
        st.success("Analysis complete!")

        st.subheader("💡 Insights")
        for insight in result["insights"]:
            st.write(f"- {insight}")

        if result["charts"]:
            st.subheader("🖼️ Charts")
            # No backend, no URL -- analyze_csv_file() already returns
            # local file paths (e.g. outputs/chart_1.png), and the
            # carousel reads them straight off disk. Phase 27: a
            # left/right-navigable, click-to-zoom carousel instead of a
            # plain vertical stack of images.
            render_chart_carousel(result["charts"])
    else:
        st.error(f"Analysis failed: {result['error']}")

    # Phase 26: one self-contained HTML report bundling everything above
    # -- offered as a download regardless of success/failure, same
    # "renders unconditionally" pattern as Data Health.
    if result.get("report_path"):
        with open(result["report_path"], "rb") as f:
            st.download_button(
                "📄 Download full report (HTML)",
                data=f.read(),
                file_name="analysis_report.html",
                mime="text/html",
            )

    # Phase 19: natural language data chat. Only shown once a dataset has
    # actually been analyzed (we need uploaded_bytes to rebuild a temp
    # CSV file for each question -- run_code()'s wrapper script reads the
    # file from a real path, it doesn't accept an in-memory DataFrame).
    if "uploaded_bytes" in st.session_state:
        st.subheader("💬 Ask a follow-up question")

        for turn in st.session_state.get("chat_history", []):
            with st.chat_message("user"):
                st.write(turn["question"])
            with st.chat_message("assistant"):
                st.write(turn["answer"])
                if turn.get("chart"):
                    render_chart_carousel([turn["chart"]], height=340)

        question = st.chat_input("e.g. \"Why did sales fall in March?\" or \"Plot that\"")
        if question:
            with st.chat_message("user"):
                st.write(question)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    # Re-materialize the file from the bytes kept in
                    # session_state -- the original temp file from the
                    # main analysis run was already deleted. Phase 23:
                    # reuse the original upload's extension so this
                    # rebuilt temp file gets parsed the same way.
                    chat_suffix = st.session_state.get("uploaded_file_extension", ".csv")
                    with tempfile.NamedTemporaryFile(mode="wb", suffix=chat_suffix, delete=False) as tmp:
                        tmp.write(st.session_state["uploaded_bytes"])
                        chat_tmp_path = tmp.name

                    try:
                        chat_df = load_data_file(chat_tmp_path)
                        chat_profile = profile_dataframe(chat_df)
                        chat_result = answer_data_question(
                            chat_profile,
                            chat_tmp_path,
                            question,
                            conversation_history=st.session_state.get("chat_history", []),
                            quality_report=st.session_state["result"].get("data_quality"),
                        )
                    finally:
                        os.remove(chat_tmp_path)

                if chat_result["success"]:
                    st.write(chat_result["answer"])
                    if chat_result["chart"]:
                        render_chart_carousel([chat_result["chart"]], height=340)
                    st.session_state["chat_history"].append({
                        "question": question,
                        "answer": chat_result["answer"],
                        "chart": chat_result["chart"],
                    })
                else:
                    st.error(f"Couldn't answer that: {chat_result['error']}")

    # Phase 22: SQL analyst -- a separate, alternate way to query the
    # same dataset. Kept as its own section (not merged into the chat
    # above) since it's backed by a genuinely different execution +
    # safety model (a read-only SQLite connection) rather than the
    # pandas-code-writing agent loop, and showing the generated SQL is
    # part of the point.
    if "uploaded_bytes" in st.session_state:
        st.subheader("🗄️ SQL Analyst")
        st.caption("Ask a question answered by generating and running a read-only SQL query.")

        sql_question = st.text_input("e.g. \"What is the average price by category?\"", key="sql_question_input")
        if st.button("Run SQL query") and sql_question:
            with st.spinner("Writing and running SQL..."):
                sql_suffix = st.session_state.get("uploaded_file_extension", ".csv")
                with tempfile.NamedTemporaryFile(mode="wb", suffix=sql_suffix, delete=False) as tmp:
                    tmp.write(st.session_state["uploaded_bytes"])
                    sql_tmp_path = tmp.name

                try:
                    sql_df = load_data_file(sql_tmp_path)
                    sql_result = answer_sql_question(sql_df, sql_question)
                finally:
                    os.remove(sql_tmp_path)

            if sql_result["success"]:
                st.code(sql_result["sql"], language="sql")
                if sql_result["rows"]:
                    st.dataframe(pd.DataFrame(sql_result["rows"], columns=sql_result["columns"]))
                else:
                    st.write("(query returned no rows)")
            else:
                st.error(f"Couldn't run that query: {sql_result['error']}")
