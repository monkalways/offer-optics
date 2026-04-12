-- Does the "Supp App?" field correlate with admission outcomes for the
-- supp-app-driven programs (McMaster BHSc, Queen's BHSc, Waterloo CS)?
--
-- The Supp App? field is free text in 24-25/25-26 — values include 'Yes', 'No',
-- 'KIRA', 'AIF', 'AIF, KIRA', '', etc. This query buckets them as:
--   submitted    — non-empty and not 'no'/'none'
--   not_submitted — 'no', 'none', or empty/null
--
-- Then it shows accepted-average stats per bucket. If "submitted" applicants
-- have higher average accepted averages, that's a hint that the supp app was
-- pushing borderline candidates over the line. Equally interesting if there's
-- no difference.

WITH bucketed AS (
    SELECT
        a.program_key,
        p.university,
        p.program,
        a.best_avg,
        a.decision,
        CASE
            WHEN a.supp_app_raw IS NULL
                 OR TRIM(a.supp_app_raw) = ''
                 OR LOWER(TRIM(a.supp_app_raw)) IN ('no','none','n/a','na') THEN 'not_submitted'
            ELSE 'submitted'
        END AS supp_bucket
    FROM applications a
    JOIN programs    p ON p.program_key = a.program_key
    WHERE p.program_key IN ('mcmaster_bhsc', 'queens_bhsc', 'waterloo_cs')
      AND a.cycle IN ('2024-2025', '2025-2026')
)
SELECT
    program_key,
    program,
    supp_bucket,
    COUNT(*)                                              AS n_total,
    SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END) AS n_accepted,
    SUM(CASE WHEN decision = 'rejected' THEN 1 ELSE 0 END) AS n_rejected,
    SUM(CASE WHEN decision = 'deferred' THEN 1 ELSE 0 END) AS n_deferred,
    ROUND(AVG(CASE WHEN decision = 'accepted' THEN best_avg END), 1) AS mean_avg_accepted
FROM bucketed
GROUP BY program_key, program, supp_bucket
ORDER BY program_key, supp_bucket;
