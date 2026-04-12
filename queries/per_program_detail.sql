-- Detailed breakdown for a single program. Pass with --param program=<key>, e.g.
--   python tools/run_query.py queries/per_program_detail.sql --param program=mcmaster_bhsc
--
-- Returns: per-cycle decision counts and accepted-average stats, plus a single
-- "all cycles pooled" summary row.

SELECT
    a.cycle,
    COUNT(*)                                                                     AS n_total,
    SUM(CASE WHEN a.decision = 'accepted'   THEN 1 ELSE 0 END)                   AS n_accepted,
    SUM(CASE WHEN a.decision = 'rejected'   THEN 1 ELSE 0 END)                   AS n_rejected,
    SUM(CASE WHEN a.decision = 'deferred'   THEN 1 ELSE 0 END)                   AS n_deferred,
    SUM(CASE WHEN a.decision = 'waitlisted' THEN 1 ELSE 0 END)                   AS n_waitlisted,
    ROUND(AVG(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS mean_avg_accepted,
    ROUND(MIN(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS min_avg_accepted,
    ROUND(MAX(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS max_avg_accepted,
    ROUND(AVG(CASE WHEN a.decision = 'rejected' THEN a.best_avg END), 1)         AS mean_avg_rejected
FROM applications a
WHERE a.program_key = :program
GROUP BY a.cycle

UNION ALL

SELECT
    'ALL CYCLES'                                                                 AS cycle,
    COUNT(*)                                                                     AS n_total,
    SUM(CASE WHEN a.decision = 'accepted'   THEN 1 ELSE 0 END)                   AS n_accepted,
    SUM(CASE WHEN a.decision = 'rejected'   THEN 1 ELSE 0 END)                   AS n_rejected,
    SUM(CASE WHEN a.decision = 'deferred'   THEN 1 ELSE 0 END)                   AS n_deferred,
    SUM(CASE WHEN a.decision = 'waitlisted' THEN 1 ELSE 0 END)                   AS n_waitlisted,
    ROUND(AVG(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS mean_avg_accepted,
    ROUND(MIN(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS min_avg_accepted,
    ROUND(MAX(CASE WHEN a.decision = 'accepted' THEN a.best_avg END), 1)         AS max_avg_accepted,
    ROUND(AVG(CASE WHEN a.decision = 'rejected' THEN a.best_avg END), 1)         AS mean_avg_rejected
FROM applications a
WHERE a.program_key = :program
ORDER BY cycle;
