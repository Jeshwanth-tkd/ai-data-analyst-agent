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
"""

import os
import tempfile

import streamlit as st

from app.agent.chat_agent import answer_data_question
from app.ingestion.csv_profiler import profile_csv
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
            # Phase 19: keep the raw CSV bytes around (not the temp path
            # itself, which we're about to delete) so the chat section
            # below can write a fresh temp file per question. Starting a
            # new analysis always resets the chat history -- old Q&A
            # about a different dataset shouldn't linger.
            st.session_state["uploaded_bytes"] = uploaded_file.getvalue()
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

    # Phase 17: show the plan the agent decided on before it wrote any
    # code. plan is None if planning itself failed (e.g. malformed LLM
    # response) -- code generation still works fine without it, so this
    # section just doesn't render rather than showing an error.
    plan = result.get("plan")
    if plan:
        st.subheader("Agent's Plan")
        st.write(f"**Goal:** {plan['goal']}")
        for i, step in enumerate(plan["steps"], start=1):
            st.write(f"{i}. {step}")

    # Phase 18: deterministic EDA charts, independent of the LLM run --
    # shown regardless of success/failure below, same reasoning as Data
    # Health above.
    auto_charts = result.get("auto_eda_charts")
    if auto_charts:
        with st.expander(f"Automatic EDA ({len(auto_charts)} charts, no LLM involved)"):
            for chart_path in auto_charts:
                st.image(chart_path)

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

    # Phase 19: natural language data chat. Only shown once a dataset has
    # actually been analyzed (we need uploaded_bytes to rebuild a temp
    # CSV file for each question -- run_code()'s wrapper script reads the
    # file from a real path, it doesn't accept an in-memory DataFrame).
    if "uploaded_bytes" in st.session_state:
        st.subheader("Ask a follow-up question")

        for turn in st.session_state.get("chat_history", []):
            with st.chat_message("user"):
                st.write(turn["question"])
            with st.chat_message("assistant"):
                st.write(turn["answer"])
                if turn.get("chart"):
                    st.image(turn["chart"])

        question = st.chat_input("e.g. \"Why did sales fall in March?\" or \"Plot that\"")
        if question:
            with st.chat_message("user"):
                st.write(question)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    # Re-materialize the CSV from the bytes kept in
                    # session_state -- the original temp file from the
                    # main analysis run was already deleted.
                    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
                        tmp.write(st.session_state["uploaded_bytes"])
                        chat_tmp_path = tmp.name

                    try:
                        chat_profile = profile_csv(chat_tmp_path)
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
                        st.image(chat_result["chart"])
                    st.session_state["chat_history"].append({
                        "question": question,
                        "answer": chat_result["answer"],
                        "chart": chat_result["chart"],
                    })
                else:
                    st.error(f"Couldn't answer that: {chat_result['error']}")
