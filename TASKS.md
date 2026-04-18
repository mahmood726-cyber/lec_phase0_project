# TASKS — Phase 0 Bronze (Execution Order) [COMPLETE]

## 0A — Core Scaffold [DONE]
- CLI skeleton: `lec run`, `lec verify`, `lec build`, `lec discovery ...`
- hashing + manifest writer
- output directory conventions
- schema validation harness

## 0B — MVP Validators (4) [DONE]
- effect_direction (with negation and extreme value detection)
- inconsistent_n (with zero-event detection)
- units_timepoint
- duplicates

## 0C — Provenance (Critical Fields Only) [DONE]
- provenance schema + tracker
- source locators (file/page/bbox) supported
- provenance validator: every critical field has provenance

## 0D — Multi-agent Extraction (Pilot) [DONE]
- Agent A: deterministic rules-based extractor
- Agent B: independent extractor (LLM profile)
- comparator emits field-level disagreements

## 0E — TruthCert (Bronze) [DONE]
- orchestrates: provenance checks + 4 validators + disagreement summary
- decision: PASS / FLAG / FAIL + reasons
- scorecard + immutable audit log + certificate JSON

## 0F — MetaEngine Bridge (JSON Contract) [DONE]
- prepares MetaEngine input JSON from verified extraction
- runs demo meta-analysis (hksj)
- parses MetaEngine output JSON back into LEC analysis results

## 0G — CT.gov via AACT (Pilot Scope) [DONE]
- restore AACT snapshot locally (demo mode supported)
- run MeSH-based SQL candidate query
- triage INCLUDE/FLAG/EXCLUDE with reason codes

## 0H — Europe PMC OA Index (Pilot) [DONE]
- OA availability index for pilot paper set
- Streaming PDF downloader

## 0I — Linking (MVP) [DONE]
- deterministic ID matching + confidence score
- fuzzy title matching with normalization

## 0J — Assemble First LEC Object [DONE]
- include TruthCert + MetaEngine contract + manifest references
- write `outputs/lec_objects/<topic>.json`

## 0K — Zenodo Pack [DONE]
- zip artifact bundle + methods template
- produce DOI-ready release folder with metadata

---

Deliverable of Phase 0 Bronze:
A single end-to-end, citable LEC object for the pilot topic.
