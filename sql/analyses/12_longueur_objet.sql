-- Subject line length vs open rate, in buckets of characters.
SELECT CASE
         WHEN length(c.subject) < 30 THEN '1. under 30'
         WHEN length(c.subject) < 50 THEN '2. 30 to 49'
         WHEN length(c.subject) < 70 THEN '3. 50 to 69'
         ELSE '4. 70 and more'
       END                                AS subject_length,
       COUNT(*)                           AS campaigns,
       ROUND(AVG(k.open_rate_pct), 2)     AS avg_open_rate_pct
FROM v_campaign_kpis k
JOIN dim_campaign c USING (campaign_id)
WHERE c.subject IS NOT NULL
GROUP BY subject_length
ORDER BY subject_length;
