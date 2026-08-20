# Project Audit — Pre-Upgrade Snapshot

*Written before any upgrade code is touched, per the "audit first" rule.
This is the honest state of the repo as it exists today — not what it
could become. See `ARCHITECTURE_BEFORE.md` for the diagram, and
`FUTURE_ROADMAP.md` for the full backlog of ideas we're deliberately
NOT building right now.*

---

## 1. Current architecture

Four-module pipeline under `app/`, each mapping to one build phase of
the original 11-phase build:

```
app/ingestion/csv_profiler.py   → load + profile a CSV into a dict
app/agent/llm_client.py         → dataset profile → Groq LLM → Python code (string)
app/executor/code_executor.py   → run that code in a subprocess, self-correct on failure
app/output/insights.py          → structure results; analyze_csv_file() is the one hardened entry point
```

Two consumers of `analyze_csv_file()`:
- `main.py` — FastAPI backend (built, tested, **not** the live deployment)
- `streamlit_app.py` — Streamlit frontend, calls the pipeline **in-process** (the live deployment, since Phase 10)

## 2. Current data flow

CSV upload (Streamlit `st.file_uploader`) → bytes written to a temp file
→ `analyze_csv_file(path)` → `profile_csv()` (ingestion) →
`generate_analysis_code(profile)` (agent, first attempt) →
`run_code()` (executor, subprocess) → on failure: `generate_analysis_code(profile, previous_code, error)`
→ retry (up to 4 attempts total) → on success: `parse_insights()` +
`list_chart_files()` (output) → result dict rendered by Streamlit.

## 3. Current agent loop

Single-agent, single-tool, linear retry loop — not a planner, not
multi-step. One LLM call produces one complete script; there is no
intermediate "plan," no tool selection, no state beyond
(code, error) passed back into the next prompt. Retries are capped at 3
(4 attempts total), each attempt logged in an `attempts` list returned
to the caller. This is deliberately simple and it is the project's
current honest limitation, not a hidden one — see Section 9.

## 4. Current security model

- Generated code runs in an OS **subprocess** (`subprocess.run`), not
  `exec()` in-process — real crash/hang isolation via a hard 15s
  timeout, but **not** a security sandbox: the subprocess has the same
  filesystem/network/OS permissions as the rest of the app.
- No AST inspection of generated code before execution. Nothing today
  stops generated code from doing `import os; os.system(...)`,
  `import socket`, or reading arbitrary files on disk — it is only
  constrained by a system-prompt instruction ("only pandas and
  matplotlib"), which is a request, not an enforcement mechanism.
- No allowlist/blocklist, no static analysis, no resource limits beyond
  the timeout.
- **This is the single highest-leverage gap to close** — it's cheap,
  it's real, and "I added static analysis to reject dangerous
  operations before ever executing LLM-generated code" is a genuinely
  strong interview answer that today's project can't fully give yet.

## 5. Current frontend architecture

`streamlit_app.py` — single-page Streamlit app. File uploader → button
gate (`st.button("Analyze")`, since Streamlit reruns the whole script on
every interaction) → `st.session_state` caches the result across reruns →
insights rendered as text, charts via `st.image(local_path)`. No
multi-page routing, no auth, no history, no conversation state.

## 6. Current backend architecture

`main.py` — FastAPI, two endpoints (`GET /` health check,
`POST /analyze`), charts served as static files under `/charts`. Thin by
design — it exists to prove the pipeline can be exposed as a real API,
but it is **not** what the live Streamlit Cloud deployment uses (see
Phase 10 pivot in `README.md`).

## 7. Current deployment architecture

Single Streamlit process on Streamlit Community Cloud, calling the
pipeline in-process. `main.py` + `Dockerfile` are real, tested, standalone
artifacts, not wired into the live deployment. Secrets via Streamlit
Cloud's dashboard, injected as an environment variable at runtime.

## 8. Current testing strategy

`tests/benchmark_agent.py` and `tests/manual_eda_timer.py` are
**benchmarking** scripts (measure elapsed time, print a table), not a
`pytest` test suite. There are currently **zero automated correctness
tests** — no unit tests on `csv_profiler.py`'s edge cases, no test that
`run_code()` actually times out, no regression tests. This is a real,
honest gap (already flagged earlier in this project's own "What I'd
improve" section) and is one of the phases in the scoped upgrade below.

## 9. Current limitations (already documented, restated here for completeness)

- Subprocess sandboxing, not container/AST-based sandboxing (Section 4).
- Fixed retry limit (3) and timeout (15s), not tuned against real data.
- Chart-serving assumes a shared local filesystem (fine for the current
  single-process deployment; would block a stateless/serverless host).
- The "97% time saved" benchmark is one trial, one dataset, one person.
- No streaming progress — one opaque spinner.
- Column-type detection can misidentify a small-integer ID column as a
  Unix timestamp on certain malformed inputs (documented, not fixed).
- **No automated test suite** (Section 8).
- **No static/AST safety check on generated code before execution** (Section 4).

## 10. Technical debt

- `requirements.txt` still lists `requests` (used by the pre-pivot
  HTTP-based frontend); harmless but no longer load-bearing.
- No type hints/Pydantic models anywhere — every function passes plain
  `dict`s. Fine at this size; would become a real liability if the
  system grows more moving parts (exactly what Phase 12+ below start to
  introduce carefully, not all at once).
- No structured logging — `print()` statements only, inside the agent
  loop's console output.
- No `ruff`/`mypy`/lint config — style has been consistent by hand, not
  enforced.

## 11. What can be reused as-is

`csv_profiler.py`, `llm_client.py`'s core generation logic, the overall
four-module boundary, `streamlit_app.py`'s in-process call pattern, the
README/interview-prep documentation approach. None of this needs to be
rewritten — it's the foundation the upgrade builds on top of.

## 12. What should be refactored (carefully, not rewritten)

- `run_code()` gains a **pre-execution safety-check step** in front of
  it, not a replacement of the subprocess model.
- `analyze_and_structure()` gains an optional **validation step** after
  execution succeeds, before results are returned.
- Test files move from "benchmark scripts you run by hand" to a real
  `pytest` suite that runs in CI.

## 13. What must NOT be changed

- The four-module boundary (`ingestion` / `agent` / `executor` / `output`)
  and the `agent`-decides / `executor`-runs safety separation.
- `analyze_csv_file()`'s guaranteed clean-result-dict contract — every
  new feature must still return through this shape, not break it.
- The live Streamlit deployment must keep working after every single
  change — no big-bang rewrite, no swapping to Next.js/Postgres/auth
  (that's backlog, not this round — see `FUTURE_ROADMAP.md`).
- Zero paid services, zero services requiring a credit card.

## 14. Recommended upgrade sequence (scoped, not the full 29-phase backlog)

Chosen for interview leverage per hour of work, and for not risking the
currently-working, currently-honest project. Continues the existing
README's phase numbering from Phase 11:

- **Phase 12 — Data Quality Engine + Health Score.** Deterministic
  Python, no new infra, teaches real statistics, produces a concrete
  number (`Overall: 87/100`) that's genuinely demo-able.
- **Phase 13 — AST-based Code Safety Scanner.** Closes the single
  biggest real gap (Section 4) — reject dangerous generated code
  *before* it ever reaches the subprocess. High interview payoff, no
  new paid infra, teaches Python's `ast` module and static analysis.
- **Phase 14 — Validation layer in the self-correction loop.** A
  natural, small extension of the loop that already exists — check for
  empty output, NaN-only results, etc. before declaring success.
- **Phase 15 — Real `pytest` suite + GitHub Actions CI.** Free,
  fast, closes the testing gap flagged in Section 8, and CI is a strong,
  cheap interview line ("I have a green build badge and tests actually
  run on every push").
- **Phase 16 — Richer automatic EDA.** Extends existing chart
  generation with a broader, more structured profile (distributions,
  correlations, category breakdowns) — reuses `matplotlib`, no new
  paid/heavy dependency required unless we deliberately choose to add
  Plotly for interactivity (a real, explicit decision to make together,
  not an automatic one).

Everything else in the original 29-phase document (auth, Next.js,
Postgres, RAG, AutoML/SHAP, SQL analyst, observability stack, model
routing, caching, ablation studies) is preserved verbatim in
`FUTURE_ROADMAP.md` as a backlog — genuinely good ideas, deliberately
not built right now.
