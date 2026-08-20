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
"""

import os
import tempfile

import streamlit as st

from app.output.insights import analyze_csv_file

st.set_page_config(page_title="AI Data Analyst Agent", page_icon="📊")

st.title("📊 AI-Powered Data Analyst Agent")
st.write(
    "Upload a CSV and an AI agent will write, run, and self-correct its "
    "own Python analysis code against it -- no manual EDA required."
)

uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

# st.button() only returns True on the exact rerun where it was clicked.
# Streamlit reruns this whole script on every interaction, so without
# this button as a deliberate trigger, we'd risk re-calling the LLM on
# every unrelated widget interaction -- wasteful and slow.
if uploaded_file is not None and st.button("Analyze"):
    with st.spinner(
        "Agent is thinking -- profiling your data, writing analysis code, "
        "running it, and self-correcting if it fails. This can take "
        "10-30 seconds..."
    ):
        # analyze_csv_file() needs a real file path on disk (profile_csv
        # -> load_csv opens it with pandas), but Streamlit only gives us
        # the uploaded bytes in memory. So we write those bytes out to a
        # temp file first, point the agent at that path, and clean the
        # temp file up afterwards -- the same handoff the FastAPI
        # endpoint used to do with UploadFile, just without the HTTP hop.
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            result = analyze_csv_file(tmp_path)
            # Stored in session_state so the result survives future
            # reruns (e.g. if the user interacts with something else on
            # the page) without needing to re-run the whole analysis.
            st.session_state["result"] = result
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
        st.subheader("Data Health")

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

    if result["success"]:
        st.success("Analysis complete!")

        st.subheader("Insights")
        for insight in result["insights"]:
            st.write(f"- {insight}")

        if result["charts"]:
            st.subheader("Charts")
            for chart_path in result["charts"]:
                # No backend, no URL -- analyze_csv_file() already
                # returns local file paths (e.g. outputs/chart_1.png),
                # and st.image() happily reads a chart straight off
                # disk. This is actually simpler than the old
                # BACKEND_URL + /charts/... URL version.
                st.image(chart_path)
    else:
        st.error(f"Analysis failed: {result['error']}")
