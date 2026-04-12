-- Per-program accepted-average distribution (n, min, p25, median, mean, p75, max).
-- Restricted to programs with at least 10 accepted reports so the percentiles
-- are meaningful.
--
-- Self-selection caveat: Reddit applicants over-report acceptances, so this is
-- the distribution of *admitted* averages, NOT a 50/50 cutoff line. The min
-- and p25 are the most actionable numbers — they approximate "the floor".

WITH ranked AS (
    SELECT
        program_key,
        best_avg,
        ROW_NUMBER() OVER (PARTITION BY program_key ORDER BY best_avg) AS rn,
        COUNT(*)     OVER (PARTITION BY program_key)                   AS cnt
    FROM applications
    WHERE decision = 'accepted'
      AND best_avg IS NOT NULL
      AND program_key IS NOT NULL
),
quartiles AS (
    SELECT
        program_key,
        MAX(CASE WHEN rn = MAX(1, (cnt + 2) /  4) THEN best_avg END) AS p25,
        MAX(CASE WHEN rn = MAX(1, (cnt + 1) /  2) THEN best_avg END) AS p50,
        MAX(CASE WHEN rn = MAX(1, (3 * cnt + 3) / 4) THEN best_avg END) AS p75
    FROM ranked
    GROUP BY program_key
),
agg AS (
    SELECT
        program_key,
        COUNT(*)  AS n,
        MIN(best_avg) AS min_avg,
        AVG(best_avg) AS mean_avg,
        MAX(best_avg) AS max_avg
    FROM applications
    WHERE decision = 'accepted'
      AND best_avg IS NOT NULL
      AND program_key IS NOT NULL
    GROUP BY program_key
)
SELECT
    p.tier                                  AS tier,
    a.program_key                           AS program_key,
    p.university                            AS university,
    p.program                               AS program,
    a.n                                     AS n_accepted,
    ROUND(a.min_avg, 1)                     AS min_avg,
    ROUND(q.p25,     1)                     AS p25_avg,
    ROUND(q.p50,     1)                     AS median_avg,
    ROUND(a.mean_avg,1)                     AS mean_avg,
    ROUND(q.p75,     1)                     AS p75_avg,
    ROUND(a.max_avg, 1)                     AS max_avg
FROM agg a
JOIN quartiles q ON q.program_key = a.program_key
JOIN programs  p ON p.program_key = a.program_key
WHERE a.n >= 10
ORDER BY p.tier, a.n DESC;
