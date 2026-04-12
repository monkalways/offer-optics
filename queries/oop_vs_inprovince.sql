-- For Justin's Tier-1 targets (Ontario programs), compare the accepted-average
-- distribution between Ontario residents and out-of-province applicants.
-- Justin is from Alberta, so the "out-of-province" column is the one that matters.
--
-- Province field is free-text; we treat anything containing 'ontario' (case-insensitive)
-- as in-province, and anything else (including AB / BC / international / blank) as OOP.

WITH classified AS (
    SELECT
        a.program_key,
        p.tier,
        p.university,
        p.program,
        a.best_avg,
        CASE
            WHEN a.province IS NOT NULL AND LOWER(a.province) LIKE '%ontario%' THEN 'in_province_on'
            WHEN a.province IS NULL OR a.province = '' THEN 'unknown'
            ELSE 'out_of_province'
        END AS residency
    FROM applications a
    JOIN programs    p ON p.program_key = a.program_key
    WHERE a.decision = 'accepted'
      AND a.best_avg IS NOT NULL
      AND p.tier = 1
)
SELECT
    program_key,
    university,
    program,
    residency,
    COUNT(*)                AS n,
    ROUND(MIN(best_avg),1)  AS min_avg,
    ROUND(AVG(best_avg),1)  AS mean_avg,
    ROUND(MAX(best_avg),1)  AS max_avg
FROM classified
GROUP BY program_key, university, program, residency
ORDER BY program_key, residency;
