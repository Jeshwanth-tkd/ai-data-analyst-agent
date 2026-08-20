# AI-Powered Data Analyst Agent

An agentic data analysis system: upload a CSV, Excel, JSON, or Parquet file
and it autonomously plans an analysis, writes and executes its own Python
code against your specific dataset, self-corrects when that code errors out
on malformed data, and generates insights, charts, and a downloadable report
— alongside deterministic (non-LLM) data quality scoring, automatic EDA,
anomaly detection, statistical hypothesis testing, a data cleaning agent,
time-series forecasting, a natural-language chat interface for follow-up
questions, and a read-only SQL analyst as a second way to query the data.

Built as a portfolio project, phase by phase, with a focus on understanding
every piece rather than scaffolding it all at once — the full phase-by-phase
build log is below.

**🔗 Live demo:** https://ai-data-analyst-agent-j2hnysterzf5yhjhathkqe.streamlit.app/
*(Free-tier hosting — if the app shows a "wake up" screen, it just went to sleep from inactivity; one click and it's back in ~15 seconds.)*

## Screenshots

*(Updated screenshots coming soon — the ones previously here were from the
original 11-phase MVP and no longer reflect the current UI.)*

## What it does

- **Core agent loop:** plans an analysis, writes Python code against your
  dataset, executes it in an isolated subprocess, and self-corrects (up to
  3 retries) if the code errors out — feeding the real error back to the LLM
  rather than giving up.
- **Multi-format ingestion:** CSV, Excel (`.xlsx`/`.xls`), JSON, and Parquet,
  all normalized through the same safety checks (size cap, empty-file
  rejection).
- **Deterministic reports, computed with plain pandas/scipy/scikit-learn —
  zero LLM calls, so they're fast, free, and reproducible:** a data quality
  health score, automatic EDA (distributions, correlations, missingness),
  anomaly detection (per-column z-scores + Isolation Forest), automatic
  hypothesis testing (t-tests/ANOVA between categorical and numeric
  columns), a data cleaning agent (suggests and conservatively auto-applies
  fixes), and time-series forecasting (Holt's linear trend) when a
  date + numeric column pair is found.
- **Two safety layers for every code path that runs generated code:** an
  AST-based static scanner blocking dangerous imports/calls, backed by a
  structurally independent second layer — real OS-level subprocess
  isolation for Python, and a genuinely read-only SQLite connection for SQL.
- **Talk to your data two ways:** a natural-language chat agent for
  follow-up questions, and a SQL Analyst that generates and runs read-only
  SQL against the same dataset.
- **One-click downloadable HTML report** bundling every section above —
  insights, every chart (embedded, not linked), data quality, the agent's
  plan, EDA, anomalies, stats, cleaning suggestions, and forecast — into a
  single self-contained, offline-viewable file.

## Results

In a timed personal test, this agent completed first-pass exploratory data
analysis on a 200-row dataset in **6.5 seconds**, versus **3.7 minutes**
doing the same fixed checklist of analysis by hand — a **97% reduction** in
my own analysis time on that dataset (single trial, full methodology and
honest caveats in `tests/benchmark_results.md` and the Phase 9 log below).
That benchmark predates the deterministic reports, cleaning agent,
forecasting, and chat/SQL features added in later phases — it measures the
original core agent loop only, not the full current feature set.

## Why this project

Most "AI data analyst" demos just wrap an LLM around `df.describe()`. This
one is agentic in the real sense: the LLM writes actual Python analysis code
for *this specific dataset*, that code is executed in a controlled loop, and
if it fails (bad dtypes, missing values, malformed input) the error is fed
back to the LLM so it can fix its own code and retry — without a human in
the loop. It's also deliberately not *only* an LLM: every report that's
pure arithmetic (data quality, EDA, anomalies, stats) is computed
deterministically, reserving the LLM for the genuinely ambiguous judgment
calls (what to analyze, how to phrase an insight, how to answer a
free-text question) rather than routing everything through an API call.

## Architecture

```
app/
├── ingestion/    # Load + profile any uploaded file (CSV/Excel/JSON/Parquet)
├── quality/      # Deterministic data quality health score
├── eda/          # Automatic EDA summary + deterministic charts
├── anomalies/    # Z-score + Isolation Forest anomaly detection
├── stats/        # Automatic hypothesis testing (t-test/ANOVA)
├── cleaning/     # Data cleaning agent (suggest + conservatively apply)
├── forecasting/  # Time-series forecasting (Holt's linear trend)
├── agent/        # Groq LLM client, system prompts, planner, chat agent
├── executor/     # Sandboxed execution of LLM-generated code + self-correction
├── security/     # AST-based static code safety scanner
├── validation/   # Post-execution output validation (real insights? valid charts?)
├── sql/          # SQL Analyst: generation, scanner, read-only execution
├── output/       # The top-level pipeline: ties every module above together
├── report/       # Self-contained HTML report generation
└── ui/           # Reusable Streamlit UI components (chart carousel)
```

The `agent/` (decides *what* code to run) and `executor/` (actually *runs*
it) are kept as separate modules on purpose — that boundary is the core
safety design of this system, set up from day one even though the executor
itself isn't built until Phase 4. Every later addition follows the same
principle of keeping deterministic computation, LLM decision-making, and
execution/safety concerns in separate, single-purpose modules rather than
one growing file.

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

### Phase 7 — Backend API ✅
- `main.py` added: a FastAPI app with two endpoints — `GET /` (health
  check) and `POST /analyze` (accepts an uploaded CSV, runs the full
  agent pipeline, returns JSON). Deliberately thin: it just saves the
  upload to a temp file and calls Phase 6's `analyze_csv_file()` —
  virtually no new logic, since the hardened pipeline already existed.
- Chart images are served as static files (`app.mount("/charts", ...)`)
  rather than base64-encoded into the JSON response — keeps the main
  response small and fast, and is the standard REST pattern for serving
  generated files. `/analyze`'s response converts local paths like
  `outputs/chart_1.png` into fetchable URLs like `/charts/chart_1.png`.
- Verified locally (server started, hit with `curl`, and a static image
  request confirmed a real PNG came back) before relying on manual
  browser testing.
- Free interactive API docs at `/docs` (built into FastAPI) used to
  test the full upload → analyze → JSON flow — confirmed working
  end-to-end with real chart images served back correctly.
- New dependencies: `fastapi`, `uvicorn` (the server that actually runs
  a FastAPI app), `python-multipart` (required specifically for file
  upload support).

### Phase 8 — Frontend ✅
- `streamlit_app.py` added: a Streamlit UI with a file uploader and an
  "Analyze" button that calls the Phase 7 FastAPI backend over real
  HTTP (`requests.post`) — a true frontend/backend split, not a
  same-process shortcut.
- The "Analyze" click is a deliberate trigger, with the result cached
  in `st.session_state` — necessary because Streamlit reruns the whole
  script on every interaction, so without a trigger + cache, an
  unrelated click could silently re-run the (slow, LLM-calling)
  analysis.
- `BACKEND_URL` reads from an environment variable with a localhost
  default, so the deployed frontend (Phase 10) can point at a deployed
  backend without a code change.
- A spinner shows during the (10-30 second) analysis call, satisfying
  the "show progress as agent thinks" requirement from the original
  plan — full live step-by-step progress (e.g. streaming which retry
  attempt is running) would need WebSockets/SSE on the backend, which
  is a reasonable future improvement but out of scope for now.
- Verified locally by running both servers together and confirming
  both boot and respond over HTTP before manual browser testing.
- Confirmed working end-to-end: real CSV upload → live LLM analysis →
  insights and both chart images rendering correctly on the page.

### Phase 9 — Testing ✅
- Added two new sample datasets in different domains (`employee_hr.csv`,
  `movie_ratings.csv`, 200 rows each) alongside the original sales data,
  to test that the agent generalizes rather than being tuned to one
  dataset shape.
- `tests/benchmark_agent.py` times the agent's actual elapsed time
  (profile → LLM → execute → self-correct if needed) on all three.
- Built an honest human-timing methodology, since I can't fabricate a
  manual-EDA baseline: `tests/manual_eda_checklist.md` (a fixed 8-step
  checklist matching the categories of analysis the agent produces, so
  the comparison is fair) and `tests/manual_eda_timer.py` (a wall-clock
  stopwatch measuring real elapsed time — including thinking and typing,
  not just code execution, since that's what "time saved" has to mean
  for a real human doing this for the first time).
- **Measured result (single dataset, single trial, `employee_hr.csv`):
  agent completed the analysis in 6.5s vs. 3.7 minutes (224s) doing the
  same checklist manually — a 97.1% reduction in personal analysis time
  on that dataset.** Full numbers and honest caveats about scope (one
  dataset, one trial, one person) are in `tests/benchmark_results.md` —
  written deliberately to avoid overclaiming this as a general/validated
  statistic.
- Rejected citing a generic published "time saved" statistic instead of
  measuring it: researched the commonly-cited "80% of a data scientist's
  time is spent cleaning data" claim and found it (a) measures something
  different — share of overall project time, not per-dataset EDA time —
  and (b) is itself a contested, frequently-disputed figure. Using it
  here would have meant borrowing a shaky number to describe something
  it wasn't measuring.

### Phase 10 — Deployment ✅
- **Live demo:** https://ai-data-analyst-agent-j2hnysterzf5yhjhathkqe.streamlit.app/
- **Original plan vs. what actually shipped:** the plan was two separate free
  services — Streamlit for the UI, FastAPI (Phase 7) as a separately hosted
  backend, talking over HTTP, exactly as built in Phases 7-8. Getting a
  genuinely free, no-credit-card, persistent host for the *backend* turned
  out to be the real obstacle, not the frontend:
  - **Hugging Face Spaces** looked free based on their published pricing
    page, but the actual Space-creation UI showed Docker/Gradio Spaces now
    require a paid plan — a live contradiction of that earlier research,
    caught by trying to actually create one.
  - **Render** was ambiguous on whether a free web service requires a card
    on file, based on their docs alone.
  - **Vercel** is confirmed free for FastAPI, but Vercel Functions are
    stateless/serverless — a genuine architecture mismatch, not just a cost
    question: our design had one request save a chart file and a second
    request fetch it via a static file mount, and those two requests could
    land on different, disk-isolated containers with nothing shared between
    them.
- **The pivot:** rather than keep hunting for host #3, `streamlit_app.py`
  was rewritten to call `app.output.insights.analyze_csv_file()` directly,
  in-process, instead of making an HTTP request to a separately-hosted
  FastAPI backend. One Streamlit process, one filesystem, one free host
  (Streamlit Community Cloud) — the chart-sharing problem disappears
  because there's no longer a second service to share anything with.
  `BACKEND_URL`/`requests` are gone from the frontend; chart paths returned
  by `analyze_csv_file()` are passed straight to `st.image()`.
  The tradeoff: the frontend now imports directly from `app/`, so it's no
  longer a thin, swappable HTTP client — a deliberate, explainable trade
  for "actually deployed and free" over "perfectly decoupled services."
- `main.py` (the FastAPI backend) and the `Dockerfile`/`.dockerignore`
  built for it are kept in the repo even though they're no longer the
  deployment path — they're real, working artifacts that show the backend
  can run standalone (e.g. in Docker, or behind its own host later), just
  not what's live right now.
- **Real bug found on the live deployment:** a line chart with many daily
  date labels on the x-axis rendered with the labels overlapping and
  unreadable — not a pipeline bug (the chart itself was generated and
  saved correctly), but a formatting gap in what the LLM's own code wrote.
  Fixed at the source: the system prompt (`app/agent/llm_client.py`) now
  explicitly instructs the model to rotate x-axis labels when there are
  more than ~6 of them (`plt.xticks(rotation=45, ha="right")`) and to
  always call `plt.tight_layout()` before saving — so the fix applies to
  every future chart the agent generates, not just this one.
- Deployed via Streamlit Community Cloud: connected the GitHub repo,
  pointed it at `streamlit_app.py` on `main`, and added `GROQ_API_KEY` as a
  Secret through their dashboard (TOML format) rather than committing it
  anywhere — Streamlit injects it as an environment variable at runtime,
  which is exactly what `os.environ.get("GROQ_API_KEY")` already expected.
  The app auto-redeploys on every push to `main`.

### Phase 11 — Resume/Portfolio Packaging ✅
- **Backfilled entry, written retroactively:** this phase's actual work
  (final README polish, the live demo link + screenshots, an honest
  "what I'd improve" write-up) was done at the time, alongside Phase 10,
  but the log entry itself got skipped when the original 11-phase plan
  was extended into the larger phase list below — caught and filled in
  here rather than left as a silent gap in the build history.
- **Live demo link + screenshots**, both already at the top of this
  README (added right after Phase 10's deployment): the deployed app
  URL plus three screenshots (upload screen, insights/charts, chart
  detail) so a reviewer sees the working product before reading a single
  line of the build log.
- **The honest "what I'd improve with more time" section** (bottom of
  this README): written and kept up to date since this phase, covering
  subprocess-vs-container sandboxing, untuned retry/timeout constants,
  the single-process chart-serving assumption, the one-trial time-saved
  number, no streaming progress, and a known column-type-detection edge
  case — the deliberate goal being that an honest limitations list reads
  as more credible to a reviewer than a project that claims to have none.
- **The architecture write-up** — the `Architecture` section above and
  each phase's own log entry together form the "explain what you built
  and why" narrative this phase called for, rather than a single
  separate essay; kept as a running log instead of one document so it
  stays accurate as later phases (12 onward) actually change the system.

### Phase 12 — Data Quality Engine ✅
- **What it is:** a deterministic "health report" for the uploaded CSV,
  computed by `app/quality/data_quality.py` — plain pandas math, zero LLM
  calls. Reserving the LLM for genuinely ambiguous judgment calls ("what's
  interesting in this data?") and using deterministic code for
  non-ambiguous checks ("what % of this column is missing?") is a
  deliberate cost/reliability choice, not just a style preference.
- **Four sub-scores, unweighted-averaged into one overall score (0-100):**
  - *Missing values* — % of all cells that are `NaN`.
  - *Duplicates* — % of rows that are exact repeats of an earlier row.
  - *Type consistency* — text columns that are secretly numbers/dates
    stored as strings, detected by trying `pd.to_numeric`/`pd.to_datetime`
    with `errors="coerce"` and measuring what fraction actually parses.
  - *Outliers* — the classic IQR fence (`Q1 - 1.5*IQR` / `Q3 + 1.5*IQR`),
    the same rule a box plot uses to decide which points to draw outside
    the whiskers.
- **Structural flags** (not scored, just surfaced): constant columns (only
  one distinct value), ID-like columns (>95% unique — useless to group
  by), high-cardinality columns (many distinct categories — would blow up
  a bar chart), and inconsistent category spellings (`"HR"` vs `"hr"` vs
  `" HR "` silently splitting one group into several).
- **Wired in additively:** `analyze_csv_file()` gained one new result key,
  `data_quality`, computed from the *same* in-memory DataFrame the profile
  already uses (the CSV is now read once instead of twice). Every key that
  existed before is unchanged, so nothing that already consumed the result
  dict broke.
- **Surfaced in the UI** as a "Data Health" section — an overall score with
  a 🟢/🟡/🔴 badge, the four sub-scores as metrics, and an expandable
  "Structural notes" panel for the flags — rendered unconditionally
  (regardless of whether the LLM/execution side succeeded), because
  knowing your data is messy is useful even on a failed analysis run.
- **Fixed along the way:** a pandas deprecation warning
  (`select_dtypes(include="object")` → `include=["object", "string"]`) —
  left alone, it wouldn't have crashed, it would have silently stopped
  matching newer string-dtype columns in a future pandas release, which is
  worse than a crash because it fails quietly.
- **Verified before shipping:** ran the module directly against clean and
  intentionally-messy sample CSVs, an integration test with a mocked Groq
  client confirming the new key appears on both the success and failure
  paths, and a headless `streamlit run` boot check plus a scripted replay
  of the UI's exact field-access logic against real quality reports — all
  before touching git.

### Phase 13 — AST-based Code Safety Scanner ✅
- **What it closes:** `ARCHITECTURE_BEFORE.md` (Phase 0 audit) flagged
  "no security layer between code the LLM wrote and code that runs" as the
  single highest-leverage gap in the system. The old flow was
  `llm_client.py` generates code → `code_executor.py` hands it straight to
  a subprocess. The system prompt *asks* the model to only use pandas and
  matplotlib — nothing *enforced* that.
- **How it works:** `app/security/code_scanner.py` parses generated code
  into an AST (Abstract Syntax Tree) — Python's own structural
  representation of code — and walks it looking for: disallowed imports
  (`os`, `subprocess`, `socket`, `pickle`, etc.), disallowed bare builtin
  calls (`eval`, `exec`, `open`, `__import__`, `getattr`/`setattr`, etc.),
  and the classic Python sandbox-escape gadget attributes
  (`__bases__`, `__subclasses__`, `__globals__`, ...) used to reach
  dangerous functionality *without* ever writing a literal `import`
  statement. AST parsing catches all of this structurally, so it isn't
  fooled by string-concatenation or naming tricks the way a plain
  "search the code for banned words" check would be — and it doesn't
  false-positive on legitimate pandas methods that happen to share a name
  with a banned builtin (`df.eval(...)` is fine; bare `eval(...)` isn't,
  because they're different AST node shapes).
- **Wired into the existing self-correction loop, not around it:**
  `run_with_self_correction()` in `code_executor.py` now scans code
  *before* calling `run_code()`. If it's flagged, the code is never
  executed — the violation list is fed back to the LLM as if it were a
  runtime error, using the exact same retry mechanism already built for
  Phase 4, and it costs one of the same 3 retry attempts (a design
  decision made deliberately: unsafe code is treated symmetrically with
  code that crashes, rather than immediately failing the whole analysis).
- **Still honest about the limits:** this is a second, cheap, fast layer
  stacked *in front of* the subprocess sandbox from Phase 4 — it's not a
  replacement for it, and a sufficiently obfuscated payload could
  theoretically still find a gap. Defense in depth, not a silver bullet.
- **Verified before shipping:** unit-tested the scanner against safe
  pandas/matplotlib code, three realistic full analysis snippets styled
  after real agent output, every category of banned import/call, the
  sandbox-escape gadget chain, and a syntax error — then integration
  tested the full retry loop with a mocked Groq client returning unsafe
  code first and safe code on retry (confirmed: 2 API calls, unsafe code
  never reached a subprocess, final result succeeded), plus a
  never-becomes-safe case (confirmed: gives up cleanly after exactly 4
  attempts, unsafe code never executed once), plus a full
  `analyze_csv_file()` regression run and a headless `streamlit run` boot
  check to confirm Phase 12 and Phase 13 work correctly together.

### Phase 14 — Validation Layer ✅
- **What it closes:** the last gap `ARCHITECTURE_BEFORE.md` flagged — "no
  validation layer between 'code ran successfully' and 'the result is
  reported as success.'" A subprocess exit code of 0 only means the code
  didn't crash; it says nothing about whether it produced anything useful.
- **`app/validation/result_validator.py`** checks a successful run for:
  at least one real `INSIGHT: ` line in stdout, and any `chart_*.png`
  files being genuine, non-corrupt PNGs (checked via real PNG magic
  bytes, not just trusting the file extension).
- **Wired the same way as Phase 13:** a failed validation is fed back into
  the existing self-correction retry loop as if it were a runtime error,
  costing one of the same attempts, rather than a separate code path.
- **Side fix:** `outputs/` is now cleared before every individual retry
  attempt, not just once per whole analysis — otherwise a stale chart
  from an earlier failed attempt could get validated as if the *current*
  attempt had produced it.
- **Verified before shipping:** unit tests on the validator, an
  integration test where a no-insight-printed response gets caught and
  retried into a valid one, and a full `analyze_csv_file()` + headless
  `streamlit run` regression check with Phases 12-14 all active together.

### Phase 15 — pytest suite + GitHub Actions CI ✅
- **36 automated tests** across `tests/test_csv_profiler.py`,
  `test_data_quality.py`, `test_code_scanner.py`, `test_result_validator.py`,
  `test_code_executor.py`, and `test_insights.py` — covering every module
  built in Phases 2-14: ingestion edge cases (missing/empty/oversized
  files), all four data-quality sub-scores and structural flags, every
  category the AST scanner blocks (plus confirming it does NOT
  false-positive on `df.eval(...)`), the validation layer's insight/PNG
  checks, and full self-correction-loop integration tests (scanner-block-
  then-retry, validation-fail-then-retry, exhausts-retries-and-gives-up).
- **Groq is mocked everywhere** (`unittest.mock.patch` on
  `app.agent.llm_client.Groq`) — no test makes a real network call or
  needs an API key, so the suite runs identically for anyone who clones
  the repo, with zero cost and zero secrets required.
- **`.github/workflows/tests.yml`** runs the full suite on every push and
  pull request against `main` via GitHub Actions — free for public repos.
  Because nothing needs `GROQ_API_KEY`, there's nothing to configure as a
  repo secret for CI to work.
- **`requirements-dev.txt`** keeps `pytest` separate from
  `requirements.txt` on purpose, so the production install (and the
  Streamlit Community Cloud deploy) never pulls in test-only tooling.
- **Verified before shipping:** ran the full suite locally — all 36 tests
  pass — before ever pushing the workflow file, so the very first CI run
  on GitHub is expected to go green immediately.

### Phase 16 — Richer Automatic EDA ✅
- **The gap this closes:** Phase 12 (data quality) and this phase's own
  baseline stats were both being *computed* but never actually *shown to
  the LLM* — `quality_report` existed only for the user-facing UI. The
  model was re-deriving means, top categories, and correlations from
  scratch on every single call, and had no idea which columns were
  already known to be junk (constant/ID-like) or which already had a
  flagged type/outlier problem.
- **`app/eda/auto_eda.py`** (new, same "deterministic pandas, no LLM"
  pattern as Phase 12): baseline numeric stats (mean/median/std/min/max)
  per numeric column, top-5 value counts for manageable categorical
  columns, and the strongest numeric-to-numeric correlations (above a
  0.3 threshold, deduplicated, top 5).
- **Both reports now actually reach the LLM:** `quality_report` and the
  new `eda_summary` are threaded through `analyze_csv_file()` →
  `analyze_and_structure()` → `run_with_self_correction()` →
  `generate_analysis_code()`, and included on every call — the first
  attempt *and* every self-correction retry, so the context doesn't
  disappear after attempt 1. Both parameters default to `None` so every
  pre-Phase-16 call site keeps working unchanged.
- **The EDA summary excludes junk columns automatically** — it's built
  with the union of Phase 12's `constant_columns` and `id_like_columns`
  passed in as columns to skip, so the model isn't shown a "top
  categories" breakdown for something like an order ID.
- **System prompt updated** to tell the model what to do with this new
  context: don't restate a baseline stat verbatim, don't group/chart by
  constant/ID-like columns, and account for flagged type/outlier issues
  rather than silently averaging over them.
- **Verified before shipping:** 8 new unit tests for `auto_eda.py`
  (numeric stats, category frequencies, exclusion behavior,
  high-cardinality auto-skip, strong vs. weak correlation filtering,
  empty-DataFrame edge case), a scripted integration check that inspects
  the *actual* message sent to the mocked Groq client and confirms both
  reports are present in the prompt text on both the initial call and a
  retry/fix call, the full 44-test pytest suite passing, and a headless
  `streamlit run` boot check.

### Phase 17 — Multi-Step Planning Agent ✅
- **What it adds:** a separate LLM call, BEFORE any code is written, that
  decides on an explicit `AnalysisPlan` (a goal sentence + 3-5 concrete
  steps) — splitting "decide what to look at" from "write code to do it"
  instead of one call doing both at once.
- **`app/agent/planner.py`**: `generate_analysis_plan()` requests
  structured JSON (Groq's `response_format: json_object` mode) and
  validates it into a Pydantic `AnalysisPlan` model. A malformed/missing
  response falls back to a generic-but-usable plan instead of raising —
  planning is a nice-to-have, never allowed to take down the pipeline.
- **Wired everywhere `quality_report`/`eda_summary` already flow**: the
  plan is threaded through `analyze_csv_file()` → `analyze_and_structure()`
  → `run_with_self_correction()` → every `generate_analysis_code()` call,
  initial attempt and retries alike.
- **Shown in the UI** as "Agent's Plan" — the goal and numbered steps,
  rendered before the analysis even starts running.
- **Verified before shipping:** unit tests covering a valid structured
  response, a malformed-JSON fallback, a schema-mismatch fallback, and
  the prompt-formatting helper; an insights-level test confirming a
  planner failure (real network/auth error, unmocked on purpose) doesn't
  break the overall pipeline.

### Phase 18 — Automatic EDA Engine (deterministic charts) ✅
- **What it adds:** a second, LLM-independent chart set, generated
  directly from the DataFrame every run — distribution histograms for
  the most variable numeric columns (ranked by coefficient of variation,
  capped at 4), a correlation heatmap, and a missingness bar chart. Same
  "deterministic pandas/matplotlib, no LLM" philosophy as
  `data_quality.py`/`auto_eda.py`, but producing charts instead of stats.
- **`app/eda/auto_charts.py`**: matplotlib (already a dependency) rather
  than adding Plotly, so charts stay on the same static-PNG delivery path
  (`st.image`) already used everywhere else.
- **Always available**, independent of whether the LLM's own run
  succeeds — computed in `analyze_csv_file()` before the agent loop even
  starts, attached as `auto_eda_charts` (a list of file paths).
- **Shown in the UI** in an "Automatic EDA" expander.
- **Verified before shipping:** unit tests for chart generation, the
  single-numeric-column skip (no heatmap), the nothing-missing skip (no
  missingness chart), the distribution-chart cap, and that a previous
  run's files are cleared before the next — plus visual inspection of
  generated PNGs, and a scripted replay of the exact rendering logic
  used in the UI against real datasets.

### Phase 19 — Natural Language Data Chat ✅
- **What it adds:** a follow-up chat interface under the main result —
  "Why did sales fall in March?", "Show the top 10 customers", "Plot
  that" — with the last few question/answer turns kept as context so a
  vague follow-up like "plot that" can be resolved.
- **Reuses the Phase 4/13/14 engine, doesn't duplicate it**: Phase 16's
  `code_generator` injection point in `run_with_self_correction()` was
  added specifically for this — a chat question becomes a differently
  -prompted code generator (`app/agent/chat_agent.py`) plugged into the
  exact same scan → run → validate → retry loop the main analysis uses.
  Every chat answer goes through the same AST safety scanner and
  post-execution validator as a normal run, for free.
- **Session state, not a database**: conversation history and the
  original uploaded bytes are kept in Streamlit's `session_state` (the
  original temp CSV file is deleted right after the main analysis, so
  each chat question rebuilds a fresh temp file from the retained
  bytes). Starting a new analysis resets the chat history.
- **Verified before shipping:** unit tests for a plain question, a
  chart-producing question, conversation-history threading, unsafe code
  being blocked and retried through chat exactly like the main path, and
  the result shape — plus a manual multi-turn integration script
  (mocked Groq) confirming a second turn's prompt actually contains the
  first turn's Q&A and that chart files don't bleed between turns.

### Phase 20 — Anomaly Detection ✅
- **What it adds beyond Phase 12's outliers:** Phase 12 flags outliers
  one column at a time (IQR fence). This phase adds two more lenses: a
  **z-score** check per column (a different, more "classical statistics"
  definition than IQR — the two don't always agree), and, more
  importantly, **row-level multivariate anomaly detection** via
  scikit-learn's `IsolationForest` — a row that's unremarkable in every
  individual column but an unusual *combination* (e.g. very few years of
  experience paired with a very senior salary) gets caught, which no
  per-column check can do.
- **A real bug caught by testing, not assumed away:** `contamination=
  "auto"` looked like the safer, more honest choice (let the algorithm
  decide, don't assert an arbitrary threshold) — it isn't. It replays a
  fixed legacy threshold from the original 2008 Isolation Forest paper
  rather than calibrating to the data, and on real sample data here it
  flagged 65-69% of rows as "anomalous," which is obviously wrong. Fixed
  by passing an explicit `contamination=0.05` (a conventional prior, not
  a measurement) and pinned with a regression test.
- **ID-like columns are excluded** from the Isolation Forest input for
  the same reason they're excluded elsewhere — an identifier column is a
  dimension of pure noise that measurably pollutes the anomaly scores
  for every real feature it's mixed in with (also confirmed via test).
- **Verified before shipping:** 7 unit tests, including the contamination
  regression test, the ID-exclusion test, and edge cases (too few rows,
  single numeric column, empty DataFrame) — plus the full UI
  field-access replay against three real datasets.

### Phase 21 — Statistical Analysis / Hypothesis Testing Engine ✅
- **The question this answers:** Phase 16's EDA summary reports
  correlations and category breakdowns, but never says whether a
  difference is *real* or just noise. This phase adds actual hypothesis
  tests: a **two-sample t-test** for a categorical column with exactly 2
  groups, or a **one-way ANOVA** for 3-6 groups, run automatically
  against every eligible (categorical, numeric) column pair.
- **Honest about multiple comparisons:** testing many pairs and only
  reporting "significant" ones (p < 0.05) without correction is a known
  statistics trap — run enough tests and ~5% look significant by chance
  alone. No formal correction (e.g. Bonferroni) is applied, but the
  report always states how many total tests were run alongside the
  significant ones, specifically so that context isn't hidden.
- **Verified before shipping:** 7 unit tests, including a synthetic
  dataset with a genuine, known difference (correctly flagged
  significant) and one with no real difference at all (correctly NOT
  flagged) — the tests prove the statistics work, not just that the code
  runs without crashing.

### Phase 22 — SQL Analyst ✅
- **A deliberately different "front door"** onto the same dataset,
  alongside the pandas-code agent (Phase 4) and the NL chat agent (Phase
  19) — some questions are just more natural in SQL, and SQL gives a
  fundamentally different, arguably *stronger* safety model than
  sandboxing arbitrary Python.
- **Two independent safety layers, not one:** `app/sql/sql_scanner.py`
  is a Phase-13-style keyword/statement-shape blocklist (single SELECT
  or WITH/CTE only, no DROP/DELETE/UPDATE/INSERT/ALTER/PRAGMA/etc.) —
  but the real guarantee is that every query then runs through a SQLite
  connection opened in **genuine read-only URI mode**
  (`file:...?mode=ro`). Even a query that somehow slipped past the
  scanner physically cannot mutate the database, because the OS-level
  connection doesn't have write permission — proven directly in tests by
  handing an `UPDATE` straight to the read-only connection (bypassing
  the scanner entirely) and confirming SQLite itself rejects it.
- **Same generate → check → run → retry shape** as the Python agent
  loop, implemented separately (not reusing `code_executor.py`, which is
  built around subprocess execution that doesn't apply to SQL) — a scan
  failure or a real SQL error both feed back into another LLM call, up
  to 3 retries.
- **Shown in the UI** as its own "SQL Analyst" section — the generated
  SQL is displayed alongside the result table, not hidden, since seeing
  the actual query is part of the point.
- **Verified before shipping:** unit tests for the scanner (including a
  false-positive check — a column named `dropoff_location` must NOT be
  blocked just because "drop" is a substring), unit tests for the full
  analyst loop (happy path, scanner-block-then-retry, SQL-error-then-
  retry, exhausts-retries-and-gives-up), and — critically — a direct test
  proving the read-only connection rejects a write with zero scanner
  involvement at all.

### Phase 23 — Multi-format Ingestion ✅
- **Uploads are no longer CSV-only.** `app/ingestion/csv_profiler.py`
  gains `load_data_file()`, a dispatcher that routes Excel (`.xlsx`/`.xls`),
  JSON (`.json`), and Parquet (`.parquet`) files to their own loaders
  (`pd.read_excel`/`read_json`/`read_parquet`), alongside the original,
  unchanged `load_csv()`. Every format gets the identical size-cap and
  empty-check safety guarantees — factored into shared `_enforce_size_cap()`
  / `_reject_if_empty()` helpers rather than reimplemented per format.
- **A real bug caught by testing, not just the ingestion layer:** the
  self-correction loop's subprocess wrapper (`code_executor.py`'s
  `run_code()`) hardcoded `pd.read_csv(...)` as the very first line of
  every generated script — so an Excel/JSON/Parquet upload would load
  fine at the profiling stage but then crash on attempt 1 of the LLM
  loop, retry, and crash identically 3 more times (the failure is in the
  fixed wrapper preamble, before any LLM-generated code runs, so no
  amount of "fixing" the generated code could ever help). Caught by an
  end-to-end replay test that ran the *actual* mocked-Groq pipeline
  against real `.xlsx`/`.json`/`.parquet` sample files, not just a direct
  call to the ingestion function. Fixed with `_build_load_statement()`,
  which dispatches the wrapper's load line by extension the same way
  `load_data_file()` does.
- **The Streamlit UI's file uploader, chat rebuild, and SQL Analyst
  rebuild** all updated to preserve the original upload's file extension
  (kept in `session_state` alongside the raw bytes) rather than assuming
  `.csv` for every temp file they write.
- **Verified before shipping:** unit tests for every new loader (happy
  path, corrupt file, oversized file, empty-after-load, unsupported
  extension) and for the subprocess wrapper's load-statement dispatch,
  plus a full pipeline replay (ingestion → planning → code generation →
  execution → charts → anomalies → stats) against real sample files in
  all three new formats, plus a headless Streamlit boot check.

### Phase 24 — Data Cleaning Agent ✅
- **`app/cleaning/data_cleaning.py`** turns Phase 12's deterministic
  quality report into concrete, human-readable suggestions:
  `suggest_cleaning_actions()` never touches the data, so it's always
  safe to compute and show; `apply_cleaning_actions()` is a separate,
  explicit step that performs a conservative auto-applied subset (fill
  missing numeric values with the column median, fill missing
  categorical values with `"Unknown"`, drop exact-duplicate rows,
  standardize inconsistent category spellings to the most common
  original casing) on a **copy** of the DataFrame — the caller's
  original data is never mutated.
- **Column drops stay suggestion-only, on purpose.** Constant columns and
  ID-like columns are flagged (`auto_applied: False`) but never dropped
  automatically — removing a whole column is a much higher-risk, harder-
  to-undo decision than filling a missing value, so it's surfaced for a
  human to decide rather than done silently.
- **Wired into `analyze_csv_file()`** as a new `"cleaning"` key
  (`{"suggestions": [...], "log": [...], "cleaned_csv_path": str|None}`),
  computed the same deterministic way as the other reports. When
  anything was actually auto-applied, the cleaned data is saved to
  `outputs/cleaned_data.csv` so the UI can offer it as a download.
- **Streamlit UI** gets a "Cleaning Suggestions" expander: auto-applied
  actions and manual-review-only suggestions are visually distinguished,
  the plain-language change log is shown, and a "Download cleaned CSV"
  button appears whenever cleaning actually changed something.
- **Verified before shipping:** unit tests for every suggestion type
  (numeric/categorical fills, duplicates, inconsistent categories,
  constant/ID-like columns staying suggestion-only) and every apply
  action, plus an explicit test proving the original DataFrame is never
  mutated, a full pipeline replay against real messy data, and a headless
  Streamlit boot check.

### Phase 25 — Forecasting ✅
- **`app/forecasting/forecasting.py`** auto-detects a date-like column
  and a numeric column, then forecasts the next several periods forward
  using Holt's linear trend method (`statsmodels`'
  `ExponentialSmoothing(trend="add", seasonal=None)`) — a deliberately
  simple, well-understood default chosen because reliably detecting a
  seasonal period on an arbitrary, possibly short, possibly
  irregular-frequency dataset is a much harder, more fragile problem,
  out of scope for this phase. A **naive baseline** (repeat the last
  observed value) is always shown alongside the model's forecast, so a
  viewer can judge whether the trend model is adding anything over
  "just guess the last number again," rather than presenting the
  model's output as unquestionably better.
- **A real design bug caught only by full-pipeline testing, not the
  module's own unit tests:** the module was first wired up to exclude
  Phase 12's "id-like columns" (>95% unique values) from its numeric
  candidate pool, mirroring how `eda_summary`/`anomalies`/
  `statistical_tests` already reuse that exclusion. That looked
  consistent in isolation, but a full-pipeline replay against a real
  daily time-series sample showed forecasting silently refusing to run
  — the one numeric metric column in the dataset (a continuous value,
  naturally >95% unique) was itself getting excluded as "id-like."
  Fixed by *not* reusing that exclusion for forecasting's numeric
  candidate at all; only genuinely constant (zero-variance) columns are
  excluded now, since date-shaped and continuous-metric columns are
  both routinely near-100%-unique by nature, which is precisely the
  shape forecasting needs, not junk to discard.
- **Every failure path returns a clean `{"ran": False, "reason": ...}`**
  rather than raising or crashing the rest of the pipeline — no date
  column found, too few historical points (fewer than 5 distinct
  dates), or an unexpected model-fit error. Most datasets in this
  project (e.g. `sample_sales.csv`, one row per near-unique date) simply
  aren't meaningful time series, so `"ran": False` is the normal,
  expected outcome for them, not an error state shown to the user.
- **Wired into `analyze_csv_file()`** as a new `"forecast"` key and into
  the Streamlit UI as a "Forecast" expander (chart + a table of
  predicted values vs. the naive baseline), shown only when a forecast
  actually ran.
- **Verified before shipping:** unit tests for detection (date+numeric
  found, no date column, no numeric column, exclude_columns behavior),
  the too-few-points and no-date failure paths, multi-row-per-date
  averaging, and a real forecast's shape/chart validity; a full pipeline
  replay against a real synthetic 60-day sales dataset
  (`data/samples/daily_sales_timeseries.csv`) that's what actually
  caught the id-like-exclusion bug above; and a headless Streamlit boot
  check.

### Phase 26 — Report Generation ✅
- **`app/report/report_generator.py`** bundles `analyze_csv_file()`'s
  entire result dict — insights, every chart, data quality, the agent's
  plan, automatic EDA, anomalies, statistical tests, cleaning
  suggestions, and forecast — into **one self-contained HTML file**.
  Every chart image is embedded directly as a base64 `data:` URI, not
  linked to a separate file, so the report is genuinely portable: one
  file that opens correctly as an email attachment, on a USB drive, or
  fully offline, with no broken image links.
- **A deliberate format decision, not a default fallen into:** HTML,
  not PDF. PDF-via-pandoc+LaTeX and PDF-via-weasyprint were both
  considered and rejected — both need a heavy system dependency (a full
  TeX Live install, or Cairo/Pango) that's slow and risky to add to
  Streamlit Community Cloud's free-tier build environment. A
  self-contained HTML file achieves the same practical "one shareable
  file with everything embedded" goal without that deployment risk —
  and a user who wants a literal PDF can still print the HTML to one
  from any browser.
- **Every section is conditional** on the data actually being present —
  the same report generator produces a clean, complete document whether
  the run fully succeeded, only the LLM step failed, or ingestion itself
  failed, mirroring the "renders unconditionally" pattern already used
  throughout the Streamlit UI.
- **User-supplied text (insight strings, error messages, column names)
  is HTML-escaped** before being embedded in the report — verified with
  a dedicated test asserting a literal `<script>` tag in an insight
  string comes out escaped, not executable, in the rendered HTML.
- **Wired into `analyze_csv_file()`** as a new `"report_path"` key
  (generated last, wrapped in its own try/except so a report-writing
  failure can never take down an otherwise-successful analysis) and into
  the Streamlit UI as a "Download full report (HTML)" button.
- **Verified before shipping:** unit tests confirming no external
  `http(s)` references exist anywhere in the output (genuine
  self-containment, not just "usually works online"), every section
  appears/disappears correctly based on the input data, the HTML-escaping
  test above, a real chart file round-tripped through the embedder and
  confirmed as a base64 `data:` URI with the original file path never
  leaking into the report, a full pipeline replay producing and
  visually inspecting a real rendered report (via a headless-browser
  screenshot) against the daily-sales time-series sample, and a headless
  Streamlit boot check.

### Phase 27 — UI/UX Polish ✅
- **A real bug caught while shipping this batch, fixed before it went
  further:** the deploy broke with an `ImportError` on
  `load_data_file` after the Phase 23-25 push — `git status` showed
  `app/ingestion/csv_profiler.py`, `app/executor/code_executor.py`, and
  several new files/directories had never actually been committed,
  even though later phases' commits (which touch `streamlit_app.py`,
  which imports from those files) had gone through. Diagnosed from the
  live Streamlit Cloud traceback plus `git status`, fixed with one
  catch-up commit adding exactly the files git showed as modified/
  untracked, confirmed live afterward.
- **`app/ui/chart_carousel.py`**: a hand-written, dependency-free
  carousel + click-to-zoom lightbox component (`streamlit.components.v1.html`),
  replacing every plain vertical stack of `st.image()` calls (Charts,
  Automatic EDA, Forecast, each chat reply's chart) — left/right arrow
  navigation, dot indicators, a slide counter, keyboard arrow-key
  support, and a full-size lightbox on click (dismissible via its close
  button, clicking outside it, or Escape). Every chart is embedded as a
  base64 `data:` URI directly in the component, the same embedding
  approach `app/report/report_generator.py` already used — no separate
  image-serving route needed.
- **Why hand-written, not a pip-installed carousel/lightbox package:**
  this project's own standing rule is free tools only, and a ~150-line
  self-contained component has no external dependency, no
  version-compatibility risk against whatever Streamlit version
  Community Cloud runs, and is small enough to fully explain in an
  interview — an actual advantage for a portfolio project, not just a
  cost-saving shortcut.
- **`components.html()` renders each call in its own `<iframe>`**, so
  multiple carousels on the same page (Charts, Automatic EDA, Forecast)
  never collide with each other's element IDs or JS state — verified by
  rendering the raw component HTML in a headless browser and clicking
  through navigation, zoom, and Escape-to-close before wiring it into
  the app.
- **A global stylesheet** (one `st.markdown(..., unsafe_allow_html=True)`
  block): the Inter font (with a system-font fallback stack so the app
  still looks reasonable if the Google Fonts request is blocked),
  rounded buttons with a consistent hover accent color, card-style
  expanders so each report section reads as a distinct block, and
  bolder metric numbers for the Data Health scores.
- **A consistent icon per section** (🩺 Data Health, 🧭 Agent's Plan, 📊
  Automatic EDA, 🚨 Anomaly Detection, 🧹 Cleaning Suggestions, 📈
  Forecast, 🧪 Statistical Tests, 💡 Insights, 🖼️ Charts, 💬 Chat, 🗄️ SQL
  Analyst) so the page is scannable at a glance instead of every section
  header looking the same.
- **A real, XSS-relevant edge case found and fixed by the carousel's own
  tests**, not just assumed safe: `json.dumps()` alone doesn't escape
  the sequence `</script>`, so a filename containing it could
  prematurely close the component's embedded `<script>` tag. Fixed with
  a small, targeted `<\/` escape and pinned with a dedicated test — even
  though a real filename can never contain `/` on a POSIX filesystem
  (making this untriggerable via an actual uploaded file today), the
  function responsible for the embedding is tested as safe on its own
  terms rather than relying on that filesystem constraint holding
  forever.
- **Verified before shipping:** unit tests for the carousel's pure
  HTML-building function (empty/missing-file handling, base64
  embedding with no raw file paths leaking out, single- vs.
  multi-chart navigation-control visibility, HTML-escaping of
  filenames, the `</script>` edge case above), a full pytest suite run,
  a headless-browser screenshot pass exercising real navigation/zoom/
  Escape-to-close interactions against the raw component HTML, a
  headless Streamlit boot check, and a browser screenshot of the live
  running app confirming the new font/styling/icons and the upload
  flow all render correctly end to end.

## Tech stack

- **LLM**: [Groq](https://console.groq.com/) free API (fast inference, no cost)
- **Language**: Python
- **Frontend + agent runtime**: Streamlit (single process — see Phase 10)
- **Also included, not currently deployed**: FastAPI backend (`main.py`) and
  a `Dockerfile`, kept as working standalone artifacts (Phase 7 / Phase 10)
- **Hosting**: [Streamlit Community Cloud](https://streamlit.io/cloud) (free)
- **File formats**: CSV, Excel (`openpyxl`), JSON, and Parquet (`pyarrow`)
  — Phase 23
- **Forecasting**: `statsmodels` (Holt's linear trend / Exponential
  Smoothing) — Phase 25
- **Testing / CI**: pytest, GitHub Actions (Phase 15)
- **Structured outputs**: Pydantic (Phase 17's `AnalysisPlan`)
- **ML / stats**: scikit-learn (Phase 20's `IsolationForest`), SciPy (Phase 21's t-test/ANOVA)
- **SQL**: SQLite (stdlib) with a read-only connection (Phase 22)

## Running locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your real GROQ_API_KEY
streamlit run streamlit_app.py
```

That's it — one command, one terminal. (The FastAPI backend in `main.py` can
still be run standalone with `uvicorn main:app --reload` if you want to hit
`/analyze` directly or explore the interactive docs at `/docs`, but the
Streamlit app no longer depends on it.)

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

No API key needed — every test that would otherwise touch the Groq API
mocks it out. This is also what runs automatically on every push via
GitHub Actions (`.github/workflows/tests.yml`).

## What I'd improve with more time

Being upfront about the rough edges, rather than hiding them, was a
deliberate goal of this project — an honest limitations list is more
credible than a project that claims to have none.

- **Sandboxing is subprocess-based, not container-based.** A subprocess
  gives real crash/hang isolation (Phase 4), but it's not a true security
  boundary — the generated code still runs with the same OS-level
  permissions as the rest of the app. A production version of this would
  run generated code in a locked-down Docker container (or a purpose-built
  sandbox like gVisor/Firecracker) with no filesystem or network access
  beyond what's explicitly needed.
- **The self-correction retry limit (3) and execution timeout (15s) are
  fixed constants, not tuned against real usage data.** With more real
  traffic I'd want to actually measure how often a 2nd vs. 3rd retry
  succeeds, and whether 15s is too tight for larger datasets, rather than
  keeping numbers I picked for reasonable-sounding defaults.
- **Chart-serving assumes a shared local filesystem** (Phase 10). That's
  fine for the current single-process Streamlit deployment, but it's the
  exact assumption that made a stateless/serverless backend host
  (Vercel) incompatible. A version meant to scale as two independent
  services would upload generated charts to object storage and pass back
  a URL instead.
- **The "97% time saved" number is one trial, one dataset, one person**
  (Phase 9) — real, honestly measured, but not something I'd present as a
  statistically validated average without running it across more datasets,
  more trials, and ideally someone other than me doing the manual side.
- **No streaming progress.** The UI shows one opaque "agent is thinking"
  spinner rather than live status per step (profiling → generating code →
  running → retrying). That would need the backend to stream updates
  (WebSockets/SSE), which is a real architecture change, not a small tweak.
- **Known, documented, not fixed:** the agent's column-type detection can
  misidentify a small-integer ID column as a Unix timestamp on certain
  malformed inputs (see Phase 6) — harmless here, but a good example of
  where I chose to document a limitation rather than spend disproportionate
  effort engineering around a rare, low-stakes edge case.
- **Forecasting's auto-detection picks the *first* numeric column, not
  necessarily the most meaningful one** (Phase 25) — on a dataset whose
  first numeric column happens to be an ID-shaped field, that's what gets
  forecast, which is technically correct but not especially useful. A
  proper fix would need either a "which column?" picker in the UI or a
  smarter heuristic (e.g. deprioritizing near-unique integer columns) —
  left as-is for now rather than guessing at a heuristic without evidence
  it actually picks better columns in practice.
