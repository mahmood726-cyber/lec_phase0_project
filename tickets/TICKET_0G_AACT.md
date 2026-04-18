# Ticket 0G — CT.gov via AACT (Pilot Scope)

## Goal
Replace fragile CT.gov API/UI text search with **AACT PostgreSQL + NLM-generated MeSH browse terms** for reliable candidate retrieval.

## Deliverables
1) AACT access
- Local restore of AACT Postgres snapshot OR hosted AACT connection
- Document connection string in `.env.example`

2) Candidate SQL (MeSH browse match)
- Use:
  - `ctgov.browse_interventions.mesh_term` for intervention concept match
  - `ctgov.browse_conditions.mesh_term` for condition concept match
  - `ctgov.studies` for status/dates
  - `ctgov.designs` for allocation/design signal

3) Triage output with **zero silent exclusions**
- INCLUDE / FLAG / EXCLUDE with mandatory `reason_codes` for every record

4) Output artifact
- `outputs/ctgov/ctgov_candidates_<topic>_<YYYYMMDD>.parquet`

## Pilot query (colchicine + MI/ACS)
See `sql/colchicine_mi_candidates.sql` in this bundle.

## Acceptance
- [ ] SQL returns candidate set using browse tables
- [ ] Output includes columns: nct_id, score_total, disposition, reason_codes
- [ ] All candidates have non-empty reason_codes
- [ ] Known relevant trials appear in the candidate set (at minimum retrieved)

## Notes
- Discovery is recall-first; precision is improved by Cochrane501 fingerprint ranker in Ticket 1-X.
