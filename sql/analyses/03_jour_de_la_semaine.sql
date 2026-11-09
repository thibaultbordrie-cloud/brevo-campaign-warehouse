-- Open rate by weekday of sending (1 = Monday).
SELECT d.weekday,
       COUNT(*)                          AS campaigns,
       ROUND(AVG(k.open_rate_pct), 2)    AS avg_open_rate_pct
FROM v_campaign_kpis k
JOIN dim_date d ON d.full_date = k.send_date
GROUP BY d.weekday
ORDER BY d.weekday;
