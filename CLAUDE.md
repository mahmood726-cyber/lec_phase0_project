# CLAUDE.md — Mahmood's Meta-Methods Coding Rules (TruthCert + OpenClaw + Supermemory)

## 1) Purpose (1–2 lines)
Ship reproducible, open-access-first meta-analysis engines and methods tooling that output **proof-carrying numbers**, with **memory that helps planning but never becomes evidence**.

## 2) The "Straight Path" (how to work)
- Start with **intent + scope**: what we will build, what we will not build, success criteria.
- Choose the **simplest correct architecture**; avoid cleverness unless it buys safety/reproducibility.
- Build an MVP that runs → add tests → add validators → ship a bundle/artefact.
- Always prefer **deterministic, inspectable** pipelines over opaque magic.

## 3) Non-negotiables (safety + integrity)
1) **OA-only**: never bypass paywalls; only use open APIs / open datasets / OA full-text where licensed.
2) **No secrets**: never print/store keys/tokens/Auth headers; redact before logs or memory.
3) **Memory ≠ evidence**: memory may guide planning only; certified claims MUST cite evidence locators + hashes.
4) **Fail-closed certification**: if validation is incomplete, output REJECT + reasons (don't "best guess").
5) **Determinism**: fixed seeds, stable sorting, pinned versions, explicit schemas.

## 4) Modular structure (keep CLAUDE.md short)
Keep this file short. Put detail into:
- `.claude/rules/` (always-on constraints: security, testing, style, data policy)
- `.claude/skills/` (on-demand workflows: "meta-analysis pipeline", "RCT ingestion", "SHAP modeling")
- `.claude/commands/` (repeatable actions: `/ship`, `/audit`, `/compact-memory`, `/index-codebase`)

If rules/skills/commands exist, follow them.

## 5) TruthCert (proof-carrying numbers) — hard requirements
### 5.1 "No naked numbers"
Any number shown to users must be:
- from **certified claims** in a TruthCert bundle, OR
- explicitly labelled **UNCERTIFIED** and kept out of certified outputs.

### 5.2 Evidence rules (required for certification)
Every certified claim must include:
- evidence locator(s) (URL/API record ID/file path within bundle)
- content hash(es) of raw inputs
- transformation/provenance steps (what code produced it)
- validator outcomes (pass/warn/block)

### 5.3 Memory-leak = BLOCK
If a claim's evidence references `memory:*` (or similar), certification must **BLOCK**.

### 5.4 Bundle-first workflow
Prefer producing small "verse-level" artefacts:
- runnable capsule + inputs + outputs + receipt/signature + audit log
- easy to re-run on miniPC clusters

## 6) OpenClaw-style "brains vs hands" loop (quality via consultation)
Use a 3-role mental model:
- **Planner**: minimal plan + risks + validators + acceptance tests
- **Builder**: implement + tests + docs
- **Verifier**: tries to break it (edge cases, drift, determinism, adversarial inputs)

Before shipping: Verifier must run and record the checks in the audit log.

## 7) Supermemory (local-first) — full pattern
### 7.1 What memory stores
Store: decisions, runbooks, conventions, failure modes, codebase maps, experiment summaries.
Do NOT store: secrets, private patient data, copyrighted text/PDF content, raw credentials.

### 7.2 Profiles (choose one per repo)
- MEMORY=OFF: no recall/capture
- MEMORY=LITE: recall before turn; capture compact summaries only
- MEMORY=FULL: recall + capture + tool-call capture (safe allowlist) + compaction + codebase indexing

### 7.3 Auto-Recall (before each "thinking turn")
If enabled, inject:
**MEMORY CONTEXT (untrusted; planning-only; NOT evidence)**
- deterministic selection order
- fixed max chars
- include memory provenance header (db hash + selection rule)

### 7.4 Auto-Capture (after each turn)
If enabled, store only:
- 3–7 bullet summary (what changed, what decided, next step)
- tags: project/module/topic
Never store full transcripts unless explicitly requested.

### 7.5 Namespace isolation
Memory must be namespaced per machine/repo (`containerTag` concept):
`<project>_<hostname>` to prevent cross-project contamination.

### 7.6 Compaction
Roll-up old items into stable summaries:
- keep references to original IDs
- never rewrite meaning
- never compact evidence (only planning context)

### 7.7 Codebase indexing
Maintain a "CodebaseIndex" memory item:
- repo hash, module map, key entry points, "do-not-touch" list, conventions

## 8) Data + modeling guardrails (meta / MASEM / SHAP / global data)
### 8.1 Global datasets (WHO / World Bank)
- version datasets + codebooks; record retrieval date + checksum
- leakage prevention: time splits / country splits where appropriate
- missingness policy explicit (imputation strategy, sensitivity runs)
- fairness warning when features can proxy sensitive attributes

### 8.2 Meta-analysis methods
Prefer modular, testable units:
- effect size calculators (RR/OR/HR/MD/SMD/Fisher-z)
- heterogeneity (tau²/I²/PI) + influence/leave-one-out
- publication bias checks (Egger's and Peters' tests)
- HKSJ adjustment for small-cluster meta-analyses (k < 10)
- Multivariate pooling with correlation sensitivity analysis
- publication bias checks clearly labelled exploratory unless validated
- MASEM: stage-1 pooled correlations + stage-2 SEM; guard non-PD matrices

## 9) Coding quality (craftsmanship)
- small files, clear names, no hidden side effects
- strong typing where possible; explicit error handling
- lint + format + tests mandatory before ship
- design for maintainability on miniPC clusters (resource-aware defaults)

## 10) Shipping ritual ("SHIP")
When I say **SHIP**:
1) run tests
2) run a demo pipeline on fixtures (no network/API keys)
3) produce a TruthCert bundle (PASS or REJECT with reasons)
4) write short release note (what changed + how verified)
5) update `.claude/rules/lessons.md` with any new mistake-prevention rule

## 11) Default assumptions (unless I override)
- Python-first for pipelines/services; browser-first for interactive apps where feasible
- offline-first tests + fixtures
- OA-only ingestion
- memory FULL for active repos, LITE for stable ones, OFF for public demo repos

## 12) Workflow Rules (from usage insights)

### Data Integrity
Never fabricate or hallucinate identifiers (NCT IDs, DOIs, trial names, PMIDs). If you don't have the real identifier, say so and ask the user to provide it. Always verify identifiers against existing data files before using them in configs or gold standards.

### Multi-Persona Reviews
When running multi-persona reviews, run agents sequentially (not in parallel) to avoid rate limits and empty agent outputs. If an agent returns empty output, immediately retry it before moving on. Never launch more than 2 sub-agents simultaneously.

### Fix Completeness
When asked to "fix all issues", fix ALL identified issues in a single pass — do not stop partway. After applying fixes, re-run the relevant tests/validation before reporting completion. If fixes introduce new failures, fix those too before declaring done.

### Scope Discipline
Stay focused on the specific files and scope the user requests. Do not survey or analyze files outside the stated scope. When editing files, triple-check you are editing the correct file path — never edit a stale copy or wrong directory.

### Regression Prevention
Before applying optimization changes to extraction or analysis pipelines, save a snapshot of current accuracy metrics. After each change, compare against the snapshot. If any trial/metric regresses by more than 2%, immediately rollback and try a different approach. Never apply aggressive heuristics without isolated testing first.

(End)
