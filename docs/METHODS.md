# METHODS — LEC Phase 0 Bronze (Template for Zenodo Pack)

## Title
A verification-first Living Evidence Composite (LEC) object pipeline for reproducible meta-analysis inputs and outputs

## What the Bronze certificate certifies
TruthCert (Bronze) certifies **traceability and reproducibility of inputs**:
- critical effect-changing fields have provenance
- validators ran and results are recorded
- multi-agent disagreement is surfaced (not hidden)
Bronze does **not** guarantee zero extraction error or completeness of the evidence universe.

## Trial discovery (CT.gov)
ClinicalTrials.gov discovery is performed via AACT PostgreSQL snapshots using NLM-generated MeSH browse terms:
- `ctgov.browse_conditions`
- `ctgov.browse_interventions`
Candidates are triaged into INCLUDE/FLAG/EXCLUDE with mandatory reason codes and zero silent exclusions.

## Precision ranking (Cochrane501)
Cochrane501 inclusion sets provide a precision layer:
- weighted term index (IDF-like)
- MA–trial bipartite graph
- co-occurrence neighbors (Jaccard)
Ranked trial candidates include provenance: which MAs and terms contributed to discovery.

## Extraction
Two extraction agents run independently:
- Agent A: deterministic rules-based extractor
- Agent B: independent extractor (LLM or alternate rules profile)
A comparator generates field-level disagreement artifacts.

## Provenance (critical fields)
Every critical effect-changing field includes provenance:
- source identifier (e.g., PMCID/DOI/PDF hash)
- locator (page, bbox) where applicable
- method/agent ID
- timestamp

## Validators (Phase 0 MVP)
1) effect_direction
2) inconsistent_n
3) units_timepoint
4) duplicates

## TruthCert decisioning
TruthCert emits PASS/FLAG/FAIL with reasons, plus an immutable audit log and certificate JSON.

## Meta-analysis computation
MetaEngine runs via a versioned JSON contract:
- metaengine_input.json (hash)
- metaengine_output.json (hash)

## LEC object assembly
The LEC object references:
- TruthCert certificate + audit log (paths + sha256)
- MetaEngine input/output (paths + sha256)
- run manifest (paths + sha256)
