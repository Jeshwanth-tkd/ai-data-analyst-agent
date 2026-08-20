# Architecture — Before the Upgrade

*A snapshot of the system exactly as it exists today, for comparison
against whatever it becomes after Phases 12+. Companion to
`PROJECT_AUDIT.md`.*

```
                              ┌─────────────────┐
                              │      USER        │
                              └────────┬─────────┘
                                       │ uploads a CSV
                                       v
                        ┌──────────────────────────────┐
                        │   streamlit_app.py            │
                        │   (Streamlit Community Cloud) │
                        │   - file_uploader             │
                        │   - Analyze button gate        │
                        │   - session_state cache        │
                        └──────────────┬─────────────────┘
                                       │ analyze_csv_file(tmp_path)
                                       │ (direct in-process call)
                                       v
                        ┌──────────────────────────────┐
                        │  app/output/insights.py        │
                        │  analyze_csv_file()             │
                        │  - guarantees clean result dict │
                        └──────────────┬───────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 v                     v                     v
      ┌───────────────────┐ ┌────────────────────┐ ┌────────────────────┐
      │ app/ingestion/      │ │ app/agent/           │ │ app/executor/        │
      │ csv_profiler.py      │ │ llm_client.py         │ │ code_executor.py      │
      │                       │ │                         │ │                         │
      │ load_csv()            │ │ generate_analysis_    │ │ run_code()              │
      │ - size cap             │ │  code(profile)         │ │  - subprocess           │
      │ - encoding fallback    │ │ - Groq API call         │ │  - 15s timeout          │
      │                        │ │ - system prompt          │ │  - matplotlib Agg       │
      │ profile_dataframe()    │ │ - returns code string     │ │                         │
      │ - shape/dtypes/nulls   │ │                            │ │ run_with_self_          │
      │ - sample rows          │ │  (called again with        │ │  correction()           │
      └───────────┬────────────┘ │   error on retry)           │ │  - up to 4 attempts     │
                  │                └──────────────┬──────────────┘ │  - loops back to agent  │
                  │                                │ generated code  │   on failure            │
                  │                                └─────────────────>                          │
                  │                                                  └────────────┬─────────────┘
                  │                                                               │ stdout/stderr
                  │                                                               v
                  │                                                  ┌─────────────────────────┐
                  │                                                  │  outputs/chart_*.png       │
                  │                                                  │  (local filesystem)         │
                  │                                                  └─────────────┬───────────────┘
                  │                                                               │
                  └───────────────────────────┬───────────────────────────────────┘
                                              v
                                 ┌─────────────────────────────┐
                                 │  Back to insights.py:         │
                                 │  parse_insights()               │
                                 │  list_chart_files()             │
                                 └─────────────┬───────────────────┘
                                              v
                                 ┌─────────────────────────────┐
                                 │  Result dict rendered by       │
                                 │  streamlit_app.py:               │
                                 │  st.write(insight)               │
                                 │  st.image(chart_path)            │
                                 └─────────────────────────────┘

  Also present, NOT wired into the diagram above (separate, standalone):
  ┌─────────────────────┐        ┌─────────────────────┐
  │ main.py (FastAPI)     │        │ Dockerfile             │
  │ POST /analyze          │        │ (containerizes main.py) │
  │ GET  /  health check   │        │ not the deployed path    │
  │ not the live deploy    │        └─────────────────────┘
  └─────────────────────┘
```

## What this diagram makes visually obvious

1. **One process, one path.** Everything from upload to rendered result
   happens inside a single Streamlit process — there is no network hop,
   no second service, no database. This is *why* the Vercel/serverless
   deployment attempt failed (Phase 10): the old design assumed two
   services sharing a filesystem; the current design doesn't need to,
   because there's only one service.
2. **No security layer between "code the LLM wrote" and "code that
   runs."** The arrow from `llm_client.py`'s output straight into
   `run_code()`'s subprocess is direct — nothing inspects that code
   first. This is the gap Phase 13 closes.
3. **No validation layer between "code ran without crashing" and "the
   result is reported as success."** `run_code()`'s `success` flag only
   means "exit code 0" — it says nothing about whether the output makes
   sense. This is the gap Phase 14 closes.
4. **`main.py` and `Dockerfile` are real but disconnected** from the
   actual request path — drawn separately on purpose, so it's visually
   honest that they exist and work, without implying they're part of
   the live flow.
