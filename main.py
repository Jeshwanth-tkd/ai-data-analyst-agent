"""
Phase 7: Backend API.

Wraps the agent (Phases 2-6) in a FastAPI web service. This file is
deliberately thin — almost all the real logic already exists in
app.output.insights.analyze_csv_file(); this layer's only job is to
accept an HTTP request, save the uploaded file, call that function,
and translate the result into an HTTP response.
"""

import os
import tempfile
from typing import Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.staticfiles import StaticFiles

from app.output.insights import analyze_csv_file, OUTPUTS_DIR

app = FastAPI(title="AI-Powered Data Analyst Agent")

# Serve everything saved in outputs/ (the chart images our agent
# produces) as static files, reachable at e.g. /charts/chart_1.png
app.mount("/charts", StaticFiles(directory=OUTPUTS_DIR), name="charts")


@app.get("/")
def health_check():
    """A simple endpoint to confirm the API is up and reachable at all."""
    return {"status": "ok", "message": "AI Data Analyst Agent API is running."}


@app.post("/analyze")
async def analyze(file: Annotated[UploadFile, File(description="A CSV file to analyze")]):
    """
    Accept an uploaded CSV, run it through the full agent pipeline
    (Phases 2-6), and return insights + chart URLs as JSON.

    This never raises an HTTP 500 for a bad or messy file —
    analyze_csv_file() already guarantees a clean result dict, success
    or failure, which we pass straight through. That's the payoff of
    building Phase 6's hardened wrapper before this phase: this endpoint
    barely has to do anything itself.
    """
    # Save the uploaded file to a temporary path on disk, since our
    # pipeline works with file paths (like the executor's subprocess
    # already does), not in-memory file objects.
    suffix = os.path.splitext(file.filename or "upload.csv")[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        result = analyze_csv_file(tmp_path)
    finally:
        os.remove(tmp_path)

    # Turn local file paths like "outputs/chart_1.png" into URLs the
    # client can actually fetch over HTTP, e.g. "/charts/chart_1.png".
    result["charts"] = [
        f"/charts/{os.path.basename(path)}" for path in result["charts"]
    ]

    return result
