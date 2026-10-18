# LEC Phase 0 Bundle (AACT + Cochrane501 Discovery)

This bundle contains:
- CLAUDE.md guardrails
- TASKS.md Phase 0 execution order
- Tickets:
  - Ticket 0G: CT.gov via AACT (with SQL)
  - Ticket 1-X: Cochrane501 Discovery (precision layer)
- Schemas:
  - lec.schema.json
  - provenance.schema.json
  - extraction.schema.json
  - truthcert.schema.json
  - discovery_result.schema.json
- configs/discovery.yaml
- sql/colchicine_mi_candidates.sql
- docs/METHODS.md (Zenodo template)

Intended workflow:
1) Restore or connect to AACT Postgres
2) Run SQL to produce `outputs/ctgov/ctgov_candidates_*.parquet`
3) Build Cochrane501 indices and rank candidates
4) Extract → validate → TruthCert → MetaEngine → assemble LEC object

## Release bundles

`ZenodoPacker.pack()` requires every artifact with a nonempty referenced path to
exist as a file. Relative references are resolved from the working directory,
as in the pipeline that creates them. An explicitly supplied methods file must
also exist; omitting it generates a README listing the included artifacts.
Metadata is preserved inside the bundle while filenames use bounded, portable
components. The ZIP replaces an existing bundle only after writing succeeds.
Packaging checks file presence, not scientific validity or reproducibility.
