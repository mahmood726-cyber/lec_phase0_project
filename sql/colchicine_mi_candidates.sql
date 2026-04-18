-- AACT candidate retrieval: colchicine + MI/ACS concepts (MeSH browse tables)
-- Query A: high-recall candidate set

WITH base AS (
  SELECT
    s.nct_id,
    s.brief_title,
    s.overall_status,
    s.study_type,
    s.phase,
    s.start_date,
    s.completion_date,
    s.last_update_posted_date,
    s.results_first_posted_date,
    d.allocation,
    d.intervention_model,
    d.masking,
    d.primary_purpose
  FROM ctgov.studies s
  LEFT JOIN ctgov.designs d
    ON d.nct_id = s.nct_id
  WHERE s.study_type = 'Interventional'
),
mesh_match AS (
  SELECT DISTINCT
    b.*,
    bi.mesh_term AS intervention_mesh_term,
    bc.mesh_term AS condition_mesh_term,
    bi.mesh_type AS intervention_mesh_type,
    bc.mesh_type AS condition_mesh_type
  FROM base b
  JOIN ctgov.browse_interventions bi
    ON bi.nct_id = b.nct_id
   AND bi.mesh_term ILIKE '%colchicine%'
  JOIN ctgov.browse_conditions bc
    ON bc.nct_id = b.nct_id
   AND (
        bc.mesh_term ILIKE '%myocardial infarction%'
     OR bc.mesh_term ILIKE '%coronary syndrome%'
     OR bc.mesh_term ILIKE '%acute coronary%'
     OR bc.mesh_term ILIKE '%st elevation%'
   )
)
SELECT *
FROM mesh_match
ORDER BY last_update_posted_date DESC NULLS LAST;

-- Query B: add simple deterministic scoring + triage

WITH candidates AS (
  SELECT DISTINCT
    s.nct_id,
    s.brief_title,
    s.overall_status,
    s.phase,
    s.last_update_posted_date,
    s.results_first_posted_date,
    d.allocation,
    d.intervention_model,
    d.masking,
    d.primary_purpose
  FROM ctgov.studies s
  LEFT JOIN ctgov.designs d ON d.nct_id = s.nct_id
  JOIN ctgov.browse_interventions bi
    ON bi.nct_id = s.nct_id
   AND bi.mesh_term ILIKE '%colchicine%'
  JOIN ctgov.browse_conditions bc
    ON bc.nct_id = s.nct_id
   AND (
        bc.mesh_term ILIKE '%myocardial infarction%'
     OR bc.mesh_term ILIKE '%coronary syndrome%'
     OR bc.mesh_term ILIKE '%acute coronary%'
     OR bc.mesh_term ILIKE '%st elevation%'
   )
  WHERE s.study_type = 'Interventional'
),
scored AS (
  SELECT
    c.*,
    CASE WHEN c.results_first_posted_date IS NOT NULL THEN 1 ELSE 0 END AS has_results,
    (CASE WHEN c.allocation ILIKE 'Random%' THEN 0.45 ELSE 0.0 END) +
    (CASE WHEN c.phase IN ('Phase 2', 'Phase 2/Phase 3', 'Phase 3', 'Phase 4') THEN 0.15 ELSE 0.0 END) +
    (CASE WHEN c.overall_status IN ('Completed','Recruiting','Active, not recruiting','Enrolling by invitation') THEN 0.10 ELSE 0.0 END) +
    (CASE WHEN c.results_first_posted_date IS NOT NULL THEN 0.10 ELSE 0.0 END) +
    0.20 AS score_total
  FROM candidates c
),
triaged AS (
  SELECT
    *,
    CASE
      WHEN score_total >= 0.75 THEN 'INCLUDE'
      WHEN score_total >= 0.55 THEN 'FLAG'
      ELSE 'EXCLUDE'
    END AS disposition,
    ARRAY_REMOVE(ARRAY[
      CASE WHEN allocation IS NULL THEN 'ALLOC_UNKNOWN' END,
      CASE WHEN allocation IS NOT NULL AND allocation NOT ILIKE 'Random%' THEN 'NOT_RANDOMIZED_FIELD' END,
      CASE WHEN phase IS NULL THEN 'PHASE_UNKNOWN' END,
      CASE WHEN overall_status NOT IN ('Completed','Recruiting','Active, not recruiting','Enrolling by invitation')
           THEN 'STATUS_LOW_SIGNAL' END
    ], NULL) AS reason_codes
  FROM scored
)
SELECT *
FROM triaged
ORDER BY score_total DESC, last_update_posted_date DESC NULLS LAST;
