# AI-Powered Data Analyst Agent

An agent that takes an uploaded CSV, autonomously writes and executes its own
Python analysis code using an LLM, generates insights and charts, and
self-corrects if the generated code errors out on malformed data.

Built as a portfolio project, phase by phase, with a focus on understanding
every piece rather than scaffolding it all at once.

## Why this project

Most "AI data analyst" demos just wrap an LLM around `df.describe()`. This one
is agentic in the real sense: the LLM writes actual Python analysis code for
*this specific dataset*, that code is executed in a controlled loop, and if it
fails (bad dtypes, missing values, malformed input) the error is fed back to
the LLM so it can fix its own code and retry — without a human in the loop.

## Architecture (evolving as we build)

```
app/
├── ingestion/   # Load + profile any uploaded CSV (dtypes, nulls, shape)
├── agent/       # Groq LLM client + the "data analyst" system prompt
├── executor/    # Sandboxed execution of LLM-generated code + self-correction
└── output/      # Structuring insights and saving charts
```

The `agent/` (decides *what* code to run) and `executor/` (actually *runs* it)
are kept as separate modules on purpose — that boundary is the core safety
design of this system, and it's set up from day one even though the executor
itself isn't built until Phase 4.

## Build log

### Phase 1 — Project setup ✅
- Folder structure created (see above), split by responsibility so each
  folder maps to a later build phase.
- `requirements.txt` started minimal (`pandas` only) — it will grow honestly
  as each phase needs a new dependency, not pre-filled up front.
- `.gitignore` set up to exclude the virtual environment, `.env` secrets,
  Python cache files, and generated chart outputs.
- `.env.example` documents the one environment variable the project needs
  (`GROQ_API_KEY`) without exposing any real secret.
- Git repo initialized and pushed to GitHub.

### Phase 2 — Core CSV ingestion ✅
- `app/ingestion/csv_profiler.py` added: `load_csv()` safely reads a CSV
  (clear errors on missing/empty/malformed files), and `profile_dataframe()`
  turns a DataFrame into a compact profile dict — shape, per-column dtype,
  null counts, unique counts, duplicate row count, and a few sample rows.
- Deliberately built by hand instead of using an auto-EDA library
  (e.g. `ydata-profiling`) — this profiling logic is what the LLM will
  reason over in Phase 3, so we need full control over its shape and content.
- Profile is a plain `dict` rather than a custom class, since it needs to
  convert cleanly to JSON/text for the LLM prompt in the next phase.
- Added `data/samples/sample_sales.csv`, a small sample dataset (10 rows,
  a few intentional missing values) used to manually verify the profiler.

### Phase 3 — LLM connection ✅
- `app/agent/llm_client.py` added: connects to Groq's free API
  (`llama-3.3-70b-versatile`) using the official `groq` Python client.
- Wrote a system prompt that constrains the LLM to a single role — given
  a dataset profile (from Phase 2), output *only* a fenced Python code
  block that analyzes a DataFrame already loaded as `df`. No chat, no
  explanation, no loading logic of its own.
- `generate_analysis_code(profile)` sends the profile as JSON in the
  user message and returns the extracted code as a plain string — it
  does **not** execute that code (that's Phase 4, kept in a separate
  `executor/` module on purpose).
- Code extraction uses a regex to pull text out of a ```` ```python ... ``` ````
  fence, with a naive fallback if the model doesn't follow instructions —
  full defensive handling of bad model output comes in Phase 6.
- API key is read from a local `.env` file via `python-dotenv`; `.env`
  itself is git-ignored and was never shared outside the developer's
  own machine.
- Added `groq` and `python-dotenv` to `requirements.txt`.

### Phase 4 — Code execution loop ✅ (the agentic core)
- `app/executor/code_executor.py` added: `run_code()` executes LLM-generated
  code in an isolated **subprocess** (not `exec()` in-process) — a crash
  only kills that subprocess, and a hang gets force-killed after a
  15-second timeout. Chosen over `exec()` for real crash/hang isolation,
  and over Docker for staying free and simple enough to build and explain
  at this stage (Docker-based sandboxing noted as a future improvement).
- `run_with_self_correction()` is the actual agent loop: generate code →
  run it → if it fails, send the exact error message back to the LLM,
  get corrected code, retry — up to 3 retries (4 attempts total) before
  honestly reporting failure. Every attempt (code, success/fail, output)
  is kept in a history list for transparency/debugging.
- `llm_client.py` extended: `generate_analysis_code()` now optionally
  accepts `previous_code` + `error_message` to build a "fix this" prompt
  instead of a fresh one — same API call, different message depending
  on whether this is a first attempt or a retry.
- Verified locally with hand-written test cases before relying on live
  LLM output: a successful run, a deliberate `NameError`, and a deliberate
  infinite loop — confirming success capture, error capture, and the
  timeout kill-switch all work correctly.

### Phase 5 — Insight & chart generation (next)
Not started yet.

## Tech stack

- **LLM**: [Groq](https://console.groq.com/) free API (fast inference, no cost)
- **Language**: Python
- **Planned**: FastAPI (backend), Streamlit (frontend)

## Running locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your real GROQ_API_KEY
```

(More detailed run instructions will be added as each phase adds runnable code.)
