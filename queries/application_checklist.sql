-- Application checklist for Justin's Tier-1 targets — flatten the requirements
-- table into a one-row-per-program checklist suitable for the dashboard.
--
-- Joins applications stats so each program row also shows the Reddit-derived
-- median accepted average and OOP-min for context.

WITH stats AS (
    SELECT
        program_key,
        COUNT(*)                                 AS n_accepted,
        ROUND(AVG(best_avg), 1)                  AS mean_accepted_avg,
        ROUND(MIN(CASE WHEN province IS NOT NULL
                        AND LOWER(province) NOT LIKE '%ontario%'
                        AND best_avg IS NOT NULL
                       THEN best_avg END), 1)    AS oop_min_observed
    FROM applications
    WHERE decision = 'accepted'
      AND best_avg IS NOT NULL
    GROUP BY program_key
)
SELECT
    r.tier,
    r.program_key,
    p.university                                          AS university,
    p.program                                             AS program,

    r.application_deadline_ouac                           AS ouac_deadline,
    r.application_deadline_supp                           AS supp_deadline,
    r.document_deadline                                   AS doc_deadline,
    r.decision_release_window                             AS decision_window,

    CASE WHEN r.supp_app_required = 1 THEN 'YES' ELSE 'no' END  AS supp_app,
    r.supp_app_type                                       AS supp_format,

    CASE WHEN r.casper_required = 1 THEN 'YES' ELSE 'no' END    AS casper,
    CASE WHEN r.interview_required = 1 THEN 'YES' ELSE 'no' END AS interview,
    CASE WHEN r.references_required = 1 THEN 'YES' ELSE 'no' END AS refs,

    r.min_average_competitive                             AS official_min_avg,
    s.mean_accepted_avg                                   AS reddit_mean_accepted,
    s.oop_min_observed                                    AS reddit_oop_min,
    s.n_accepted                                          AS reddit_n_accepted,

    r.application_fee_cad                                 AS fee_cad,
    r.confidence                                          AS confidence,
    r.source_url                                          AS source_url
FROM requirements r
JOIN programs    p ON p.program_key = r.program_key
LEFT JOIN stats  s ON s.program_key = r.program_key
ORDER BY r.tier, r.program_key;
