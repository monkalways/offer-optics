-- Year-over-year accepted-average trend for Justin's Tier-1 targets.
-- Shows whether cutoffs are creeping up, staying flat, or drifting down.
-- The 2025-2026 cycle is still in progress so its number is provisional.

SELECT
    p.program_key,
    p.program,
    a.cycle,
    COUNT(*)                                  AS n_accepted,
    ROUND(AVG(a.best_avg), 1)                 AS mean_avg,
    ROUND(MIN(a.best_avg), 1)                 AS min_avg,
    ROUND(MAX(a.best_avg), 1)                 AS max_avg
FROM applications a
JOIN programs    p ON p.program_key = a.program_key
WHERE p.tier = 1
  AND a.decision = 'accepted'
  AND a.best_avg IS NOT NULL
GROUP BY p.program_key, p.program, a.cycle
ORDER BY p.program_key, a.cycle;
