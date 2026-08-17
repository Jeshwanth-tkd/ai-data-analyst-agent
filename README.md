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
- `app/agent/llm_client.py` added: connects to Groq's free API using the
  official `groq` Python client. *(Originally used `llama-3.3-70b-versatile`;
  switched to `openai/gpt-oss-120b` after Groq deprecated that model on
  2026-08-16 — a live example of a third-party API changing under a
  running project.)*
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

### Phase 5 — Insight & chart generation ✅
- System prompt extended: the LLM may now also use `matplotlib.pyplot`
  (as `plt`), save 1-3 charts as `outputs/chart_1.png`, `chart_2.png`, etc.,
  and must prefix every genuine finding with an `INSIGHT: ` marker so it
  can be reliably separated from any other printed text.
- `app/output/insights.py` added: `parse_insights()` filters stdout for
  `INSIGHT: ` lines, `list_chart_files()` finds saved chart images,
  `clear_outputs_dir()` wipes old charts before each run so only the
  current run's images are ever present, and `analyze_and_structure()`
  ties Phases 2-5 into one call returning a clean result dict.
- `code_executor.py`'s subprocess wrapper now forces matplotlib into
  non-interactive `Agg` (file-only) mode before any generated code runs —
  a defensive measure so a stray `plt.show()` call can't hang the
  subprocess waiting on a GUI window that will never appear.
- Verified locally with hand-written fake "LLM output" before trusting
  live model output, which caught a real bug: the wrapper script wasn't
  actually importing `matplotlib.pyplot as plt` for the generated code to
  use, despite the system prompt promising it was available — fixed
  before it ever reached a real run.

### Phase 6 — Malformed-input hardening ✅
- `csv_profiler.py`: added a 5 MB file-size cap (checked before reading,
  so an oversized file is rejected instantly instead of loading first)
  and a UTF-8 → latin-1 encoding fallback for files exported from tools
  that don't use UTF-8.
- `insights.py`: added `analyze_csv_file(csv_path)`, a single hardened
  entry point wrapping the *entire* pipeline (ingestion → agent →
  executor → output) in layered error handling — specific messages for
  expected failures (bad/empty/oversized file), plus one broad backstop
  for anything unexpected. Nothing in this pipeline can crash with a raw
  traceback anymore; every path returns the same clean result shape.
  This is also the exact function Phase 7's API will call.
- Added deliberately messy sample CSVs and stress-tested against them:
  a header-only file and a truly empty file (both caught cleanly at
  ingestion, no LLM call wasted); a headerless file (pandas silently
  mistakes the first data row for headers — no crash, just wrong column
  names) and a mixed-type file (numeric columns containing stray text
  like `"N/A"`, `"twenty-five"`).
- **Real bug found and fixed during stress-testing:** on Windows, writing
  the LLM's generated code to a temp file (and running it as a
  subprocess) used the platform's default text encoding, not UTF-8.
  Windows' default can't represent some valid Unicode characters the
  model occasionally writes (e.g. a typographic dash), so it crashed
  with `'charmap' codec can't encode character...`. Fixed by explicitly
  pinning `encoding="utf-8"` for both the temp file and the subprocess
  (and `PYTHONIOENCODING=utf-8` for the child process's own stdout).
  This never appeared during development because this session's testing
  environment defaults to UTF-8 already — a real "works on my machine"
  bug, only caught because a real user tested on real Windows.
- **Self-correction proof, on real messy input, not just buggy code:**
  running the headerless CSV through the full pipeline failed on attempt
  1 and succeeded on attempt 2 — the model rewrote its own code to
  dynamically detect numeric/date/categorical columns instead of
  assuming fixed names, since the "column names" were nonsense left over
  from the missing header row. The mixed-type CSV succeeded on the
  *first* attempt, with the model proactively using
  `pd.to_numeric(errors="coerce")` on its own to handle the stray text.
- Known limitation (not fixed, intentionally): against the headerless
  file, the agent's date-detection logic misidentified a small integer
  ID column as a date (interpreting it as a Unix timestamp), producing a
  harmless but wrong "date range" insight. Left as-is and documented
  rather than specifically engineered around — a good example of an
  honest limitation for the final write-up (Phase 11).

### Phase 7 — Backend API (next)
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
