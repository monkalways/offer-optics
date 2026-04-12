-- For each Tier-1 target program, show the month-by-month histogram of when
-- decisions were received in the most recent COMPLETED cycle (2024-2025).
-- This helps Justin know when to expect news from each program.
--
-- We use the 2024-25 cycle because (a) it's complete, and (b) the live 2025-26
-- cycle is still receiving submissions and would skew toward earlier months.

SELECT
    p.program_key,
    p.university,
    p.program,
    SUBSTR(a.decision_date, 1, 7)  AS year_month,  -- 'YYYY-MM'
    COUNT(*)                       AS n_decisions,
    SUM(CASE WHEN a.decision = 'accepted' THEN 1 ELSE 0 END)  AS n_accepted,
    SUM(CASE WHEN a.decision = 'rejected' THEN 1 ELSE 0 END)  AS n_rejected,
    SUM(CASE WHEN a.decision = 'deferred' THEN 1 ELSE 0 END)  AS n_deferred
FROM applications a
JOIN programs    p ON p.program_key = a.program_key
WHERE p.tier = 1
  AND a.cycle = '2024-2025'
  AND a.decision_date IS NOT NULL
GROUP BY p.program_key, p.university, p.program, year_month
ORDER BY p.program_key, year_month;
