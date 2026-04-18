# Ticket 1-X — Cochrane501 Trial Discovery Index (Precision Layer)

## Objective
Use Cochrane501 inclusion decisions as a precision layer to rank/filter trial candidates produced by AACT (recall layer).

## Data model (canonical)
### `data/curated/cochrane501_ma.parquet`
- ma_id (string, unique)
- title (string)
- population, intervention, comparator, outcome (nullable strings)
- n_studies (int)

### `data/curated/cochrane501_trial.parquet`
- trial_key (string, unique): NCT:<id> | PMID:<id> | DOI:<id> | LABEL:<sha1>
- nct_id, pmid, doi (nullable)
- normalized_title (nullable)
- raw_label (string)
- id_source (explicit | regex_from_label | none)

### `data/curated/cochrane501_ma_trial.parquet`
- ma_id
- trial_key
- study_label

## Indices
### Term index (weighted inverted index)
`data/curated/cochrane501_term_index.parquet`
- term, term_type, df_ma, idf, sources, (optionally) ma_ids

### Co-occurrence neighbors (top-N per trial)
`data/curated/cochrane501_cooccurrence.parquet`
- trial_key, neighbor_trial_key, shared_ma_count, jaccard, rank_within_trial

## Ranking
Deterministic ranker (configurable):
score = 0.45*ma_match_score + 0.35*cooccur_score + 0.20*term_score + recency_bonus

## Evaluation (no leakage)
For held-out MA_X:
- remove MA_X from indices
- query using MA_X PICO terms
- report Recall@K and Non-GT@K
- optional: manual sample to estimate precision

## Integration
Discovery output becomes `outputs/discovery/discovery_<topic>_<date>.json` and is referenced by LEC objects under `evidence_universe.discovery_artifacts`.

## Acceptance
- [ ] Index build completes
- [ ] Term index has >= 1000 terms
- [ ] Co-occurrence index has top-N neighbors per trial
- [ ] Search runs < 2s typical
- [ ] Benchmark harness emits Recall@K and Non-GT@K
