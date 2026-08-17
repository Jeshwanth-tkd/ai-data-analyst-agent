"""
Phase 8: Frontend.

A Streamlit UI that talks to the Phase 7 FastAPI backend over real HTTP
requests -- this file has no direct knowledge of pandas, Groq, or any
agent internals. It only knows how to upload a file to /analyze and
render whatever JSON comes back. That separation is the whole point:
the backend could be swapped, redeployed, or called by something other
than this UI, and this file wouldn't need to change.
"""

import os

import requests
import streamlit as st

# Reads from an environment variable so this can point at a deployed
# backend later (Phase 10) without editing code -- defaults to your
# local FastAPI server for now.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

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
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
        try:
            response = requests.post(f"{BACKEND_URL}/analyze", files=files, timeout=120)
            response.raise_for_status()
            # Stored in session_state so the result survives future
            # reruns (e.g. if the user interacts with something else on
            # the page) without needing to re-run the whole analysis.
            st.session_state["result"] = response.json()
        except requests.exceptions.ConnectionError:
            st.error(
                f"Couldn't reach the backend at {BACKEND_URL}. Is the "
                f"FastAPI server running? (`uvicorn main:app --reload` "
                f"in a separate terminal)"
            )
        except requests.exceptions.RequestException as e:
            st.error(f"Something went wrong calling the backend: {e}")

# Render whatever the most recent result was, on every rerun -- this is
# what makes the result stick around even after the button click itself
# has passed.
if "result" in st.session_state:
    result = st.session_state["result"]

    if result["success"]:
        st.success("Analysis complete!")

        st.subheader("Insights")
        for insight in result["insights"]:
            st.write(f"- {insight}")

        if result["charts"]:
            st.subheader("Charts")
            for chart_url in result["charts"]:
                st.image(f"{BACKEND_URL}{chart_url}")
    else:
        st.error(f"Analysis failed: {result['error']}")
