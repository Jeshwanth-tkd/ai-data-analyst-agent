# Future Roadmap — Flagship Platform Backlog

**Status: aspirational backlog, NOT the active build plan.**

This is the full 29-phase "flagship, production-grade AI data analyst
platform" spec, saved here exactly as proposed, for future reference.
After discussing it, we deliberately chose **not** to build all of this
right now — see `PROJECT_AUDIT.md` Section 14 for the actual scoped
plan we're building instead (Phases 12-16, continuing the existing
project's phase numbering).

**Why this is parked instead of built immediately:** several of these
phases are full standalone projects on their own (auth + multi-user,
a full Next.js rewrite, PostgreSQL, RAG, AutoML with SHAP, a SQL analyst
with injection prevention, a Prometheus/Grafana observability stack, an
ablation study). Attempting all of it at once risks turning a small,
finished, deeply-understood project into a large, half-finished,
harder-to-defend one — worse for an interview, not better. This doc
exists so none of the thinking that went into it is lost, and so future
phases can be pulled from here deliberately, one at a time, the same
way Phases 12-16 were.

**Note on completeness:** the original spec was pasted mid-Phase 29
("CI/CD... push → lint → type check → tests → s...") and cuts off
there. Phases 1-28 below are complete as given; Phase 29 is partial.

**A few things flagged during review, worth remembering before pulling
any phase off this backlog later:**
- Several tools listed (PostgreSQL, Redis, MinIO, Next.js, Prometheus,
  Grafana, GitHub Actions) are genuinely free/open-source, but each adds
  real infrastructure to run and explain — pull them in only when a
  specific phase actually needs them, not preemptively.
- The Docker-based sandboxing phases (7-8) hit a real constraint: this
  project's cloud dev sandbox has previously failed to build Docker
  images at all (network-blocked from Docker Hub). Any local Docker
  work needs to happen on the user's own machine, not assumed to work
  here.
- "Never claim Docker sandboxing is magically secure" — good instinct,
  worth carrying into whatever security work actually gets built
  (Phase 13 in the real plan already leans this direction with AST
  analysis instead of relying on containers alone).

---

## The original spec, as provided

I already have an existing project called:
"AI-Powered Data Analyst Agent"
I want to transform it from my current working version into a FLAGSHIP, PRODUCTION-GRADE AI DATA ANALYST PLATFORM that can become the strongest project on my resume.

IMPORTANT:
DO NOT blindly rewrite everything.
DO NOT destroy working functionality.
DO NOT generate the entire project in one shot.
DO NOT hide implementation details.
DO NOT assume I already understand the technologies.

Your job is to:
1. Upgrade the existing project incrementally.
2. Teach me every concept.
3. Make me understand why every architectural decision exists.
4. Make me capable of explaining the entire project in a technical interview.
5. Use ONLY FREE / OPEN-SOURCE resources and free tiers.
6. Never introduce a paid service without explicitly asking me first.
7. Prefer local/open-source alternatives whenever possible.
8. Keep the project actually runnable at every major milestone.

### PHASE 0 — COMPLETE PROJECT AUDIT
Inspect every Python file, requirements.txt, Dockerfile, .env.example, README,
tests, configuration, frontend, backend, agent, executor, data ingestion,
output generation, deployment configuration, Git configuration.

Create PROJECT_AUDIT.md with: current architecture, current data flow, current
agent loop, current security model, current frontend architecture, current
backend architecture, current deployment architecture, current testing
strategy, current limitations, technical debt, what can be reused, what
should be refactored, what must NOT be changed, recommended upgrade sequence.

Also create ARCHITECTURE_BEFORE.md with an ASCII architecture diagram.
Do not modify application code during this phase.

*(→ done: see `PROJECT_AUDIT.md` and `ARCHITECTURE_BEFORE.md` in this repo.)*

### CRITICAL TEACHING RULE
For every new concept: what is it, why does it exist, what problem does it
solve, why do we need it in THIS project, what happens internally, what
alternatives exist, why did we choose this implementation, what are the
tradeoffs, what would happen if we removed it, how would I explain it in an
interview. Then implementation (show the file, explain architecture before
code, implement the smallest meaningful change), then line-by-line teaching
(inputs, outputs, data types, control flow, exceptions, side effects,
dependencies, security implications, why this implementation was chosen).

### NO-BLIND-CODING RULE
Before each major feature: explain the feature, the architecture, the files
that will change, the data flow, the dependencies, the failure cases.
Implement it. Run tests. Show what changed. Explain the code. Give interview
questions about that feature. Move on only after the current milestone works.
If something fails: explain what failed, why, where, how it was diagnosed,
why the fix works, and whether the fix introduces a tradeoff.

### FREE RESOURCE RULE
Use only free and open-source software or genuinely usable free tiers.
Prefer: Python, FastAPI, Next.js, TypeScript, PostgreSQL, SQLite, Redis,
DuckDB, Polars, Pandas, Scikit-learn, XGBoost, SHAP, Statsmodels, Plotly,
Docker, Pytest, Ruff, MyPy, GitHub Actions, OpenTelemetry, Prometheus,
Grafana, MinIO, Ollama, Hugging Face open-source models, Groq free tier
where appropriate. If a service requires payment, a credit card, or likely
paid usage: stop, explain free alternatives first. Do not introduce
AWS/GCP/Azure paid infrastructure unless absolutely necessary.

### TARGET FLAGSHIP ARCHITECTURE

```
                    USER
                      |
                      v
              Next.js Frontend
                      |
                 REST / SSE
                      |
                      v
               FastAPI API
                      |
          +-----------+-----------+
          |                       |
          v                       v
   Authentication            Agent Engine
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
       Data Profiler       Planning Agent       Data Quality
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                         Analysis Executor
                                  |
                           Security Layer
                                  |
                         Docker Sandbox
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
         Statistics          Machine Learning      Visualization
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                         Validation Agent
                                  |
                                  v
                          Insight Generator
                                  |
                                  v
                         Report Generator
                                  |
                     +------------+------------+
                     |                         |
                     v                         v
                PostgreSQL               Object Storage
```
The architecture can evolve incrementally. Do NOT implement everything at once.

### FLAGSHIP FEATURES (implement in logical order — this list is the backlog)

**PHASE 1 — Architecture refactor.** Clean project structure, configuration
management, dependency management, typed models, logging, error handling,
service boundaries, environment configuration. Teach: clean architecture,
separation of concerns, dependency injection, Pydantic, configuration
management, typed Python, logging.

**PHASE 2 — Professional data ingestion.** Support CSV, Excel, JSON, Parquet,
eventually SQL databases. Teach: file parsing, schema inference, data types,
memory considerations, large dataset handling, Polars vs Pandas, DuckDB.

**PHASE 3 — Advanced data quality engine.** Detect missing values, duplicates,
incorrect data types, constant columns, ID columns, date columns, high
cardinality, outliers, inconsistent categories, invalid values, suspicious
distributions, correlations, possible leakage. Generate a Data Health Score
(e.g. Overall: 87/100, Missing values: 94/100, Type consistency: 81/100,
Duplicates: 98/100, Outliers: 73/100). Teach every statistical/data-quality
technique.

**PHASE 4 — Data cleaning agent.** Detect problems, explain them, recommend
fixes, ask for confirmation when appropriate, apply transformations, record
every transformation, preserve original data. Create cleaning_log.json.
Teach: immutable/raw data, transformation pipelines, reproducibility, audit
logs, data lineage.

**PHASE 5 — Multi-step planning agent.** Don't immediately generate Python:
understand task → inspect dataset → create analysis plan → execute plan →
observe result → validate → revise plan if necessary → final answer. Teach:
agentic systems, planning, tool use, state, observation, action, feedback
loops, deterministic vs LLM-driven steps. Create an explicit AnalysisPlan
with Pydantic models.

**PHASE 6 — Natural language data chat.** Support conversational questions
("Why did sales fall in March?", "Show the top 10 customers.", "Plot that.",
"Why?") with maintained conversation context. Teach: conversational state,
context management, structured outputs, tool calling, query planning,
ambiguity handling.

**PHASE 7 — Secure code execution.** Upgrade from subprocess isolation
toward: LLM-generated code → AST validation → security policy → Docker
sandbox → resource limits → no network → restricted filesystem → timeout →
result extraction. Teach deeply: arbitrary code execution risks, subprocess
vs container, sandboxing, Linux isolation concepts, Docker, resource limits,
attack surfaces, AST parsing, allowlists vs blocklists, defense in depth.
Never claim Docker sandboxing is magically secure — explain its limitations.

**PHASE 8 — Code safety scanner.** Parse generated Python using AST before
execution; detect/reject dangerous operations (os.system, subprocess, socket,
requests, eval, exec, unsafe file access, network access). Use an allowlist
wherever practical. Teach: Python AST, static analysis, security policy,
threat modeling. Add adversarial tests.

**PHASE 9 — Self-correction + validation agent.** Upgrade the loop to:
generate → execute → observe → validate → correct → retry. Validation checks
empty output, NaNs, inconsistent numbers, impossible results, invalid
charts, failed statistical assumptions, mismatched conclusions. Create a
structured ValidationResult. Teach: reliability, verification, hallucination
mitigation, deterministic validation, retry policies.

**PHASE 10 — Automatic EDA engine.** Generate dataset overview,
distributions, correlations, category analysis, numerical summaries, time
trends, missingness analysis, outliers, important relationships. Use Plotly
for interactive visualizations. Teach: EDA, visualization principles, chart
selection, misleading visualizations, statistical interpretation.

**PHASE 11 — Anomaly detection.** Support IQR, Z-score, Isolation Forest;
eventually time-series anomaly detection. Explain when each method is
appropriate. Show anomaly score, reason, supporting evidence.

**PHASE 12 — Statistical analysis engine.** Support mean, median, variance,
standard deviation, covariance, correlation, confidence intervals, t-tests,
chi-square, ANOVA, regression, p-values. Teach every method from
fundamentals. Do not let the LLM invent statistical conclusions — use
deterministic Python/statistical libraries.

**PHASE 13 — Automatic ML / AutoML.** Determine whether the dataset supports
classification, regression, clustering, anomaly detection, or time-series
forecasting; create appropriate pipelines; compare models; show
accuracy/precision/recall/F1/ROC-AUC/MAE/RMSE/R² as appropriate. Teach:
train/validation/test, cross-validation, data leakage, feature engineering,
preprocessing, model selection, hyperparameters, evaluation.

**PHASE 14 — Model explainability.** Use SHAP where appropriate; generate
explanations (prediction → important features → direction → contribution).
Teach: feature importance, SHAP, local/global explanations, limitations of
explainability.

**PHASE 15 — Forecasting.** Automatically detect time-series problems;
support at least baseline forecasting, moving average, statistical
forecasting where appropriate, using free/open-source libraries. Show
forecast, confidence interval, trend, seasonality if detected. Teach
time-series fundamentals.

**PHASE 16 — Hypothesis generation.** Generate hypotheses from data (e.g.
"H1: Revenue increased because order volume increased"), test them using
deterministic analysis, return Supported / Not supported / Insufficient
evidence. Teach: hypothesis testing, correlation vs causation, experimental
reasoning, statistical evidence.

**PHASE 17 — SQL analyst.** Add database support (SQLite, DuckDB,
PostgreSQL). Natural language → SQL generation → SQL validation → read-only
execution → result validation → explanation. Absolutely prevent destructive
SQL. Teach: relational databases, SQL, joins, indexes, query planning, SQL
injection, read-only credentials, generated SQL validation.

**PHASE 18 — RAG for data documentation.** Allow uploading data dictionaries,
business rules, KPI definitions, documentation; question → retrieval →
relevant context → answer. Use free/open-source embeddings/vector database
where possible. Teach: embeddings, chunking, vector search, retrieval, RAG,
grounding, hallucination. Do not add RAG just for buzzwords — it must solve
a real problem.

**PHASE 19 — Report generation.** Generate professional PDF/HTML reports:
executive summary, dataset health, key findings, charts, statistical
results, ML results, anomalies, forecast, recommendations, methodology,
limitations. Make reports reproducible.

**PHASE 20 — Real-time agent trace.** Replace the opaque loading spinner
with live progress (e.g. "✓ Dataset uploaded / ✓ Profiling / ✓ Data quality
scan / ✓ Creating plan / ✓ Generating code / ⚠ Attempt 1 failed / ✓
Self-correction / ✓ Execution / ✓ Validation / ✓ Report generated"). Use
Server-Sent Events (SSE) first unless WebSockets are genuinely needed. Teach:
streaming, SSE, async programming, event-driven systems, frontend state
updates.

**PHASE 21 — Project history.** Let users save datasets, analyses,
conversations, generated code, charts, reports, model results, analysis
plans, using PostgreSQL or SQLite locally. Teach: database schema design,
ORM, migrations, relationships, indexing.

**PHASE 22 — Authentication.** Implement proper authentication, preferring
free/open-source solutions. Teach: password hashing, JWT/session concepts,
authentication vs authorization, user isolation, RBAC, secrets.

**PHASE 23 — Observability.** Add structured logs, request IDs, latency,
agent retries, LLM calls, execution time, errors, success rates; if
feasible, OpenTelemetry/Prometheus/Grafana, all free/open-source. Teach:
observability, metrics, logs, traces, SRE fundamentals.

**PHASE 24 — Evaluation framework.** Build a benchmark suite across multiple
datasets (clean, missing values, malformed, mixed types, categorical, time
series, outliers, large). Measure code execution success, analysis
correctness, validation success, self-correction rate, latency, LLM calls,
token usage, failure rate. Create an evaluation/ folder with automated
benchmark scripts and charts. Teach: AI evaluation, benchmark design,
reproducibility, metrics, statistical validity.

**PHASE 25 — Ablation study.** Compare baseline LLM vs. +profiling vs.
+planning vs. +self-correction vs. +validation vs. full agent on success
rate, latency, failure rate, retries. Create an evaluation report
demonstrating whether each architectural component actually improves
performance.

**PHASE 26 — Model routing.** Route simple tasks to a fast/small model,
complex reasoning to a stronger model; use a local model (Ollama/open-source)
where sufficient. Teach: model routing, latency, cost, quality, fallback
strategies.

**PHASE 27 — Caching.** Cache safe deterministic operations (dataset
profiling, repeated questions, repeated computations). Teach: hashing, cache
keys, invalidation, Redis, deterministic vs non-deterministic results.

**PHASE 28 — Testing.** Build unit, integration, API, agent, security,
adversarial, and regression tests, plus evaluation tests, using pytest.
Teach: mocking, fixtures, integration testing, test isolation, regression
testing, test-driven thinking.

**PHASE 29 — CI/CD.** GitHub Actions pipeline: push → lint → type check →
tests → *(spec cuts off here in the original paste — deploy step and beyond
were never provided)*.

---

*If we come back to pull a phase off this list later, treat it the same
way Phases 12-16 were handled: audit the relevant part of the current
code first, confirm the scope and any new dependency explicitly, then
teach-then-build it as its own mini-project — not bolted on all at once.*
