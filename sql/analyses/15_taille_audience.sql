-- Audience size vs engagement: are small targeted sends better than large ones?
SELECT CASE
         WHEN delivered < 10000  THEN '1. under 10k'
         WHEN delivered < 100000 THEN '2. 10k to 100k'
         WHEN delivered < 500000 THEN '3. 100k to 500k'
         ELSE '4. 500k and more'
       END                                AS audience_size,
       COUNT(*)                           AS campaigns,
       ROUND(AVG(click_rate_pct), 2)      AS avg_click_rate_pct,
       ROUND(AVG(unsub_rate_pct), 3)      AS avg_unsub_rate_pct
FROM v_campaign_kpis
WHERE delivered > 0
GROUP BY audience_size
ORDER BY audience_size;
