-- Local vs national, month by month: is the gap stable over time?
SELECT d.year, d.month, k.scope,
       COUNT(*)                           AS campaigns,
       ROUND(AVG(k.click_rate_pct), 2)    AS avg_click_rate_pct,
       ROUND(AVG(k.unsub_rate_pct), 3)    AS avg_unsub_rate_pct
FROM v_campaign_kpis k
JOIN dim_date d ON d.full_date = k.send_date
GROUP BY d.year, d.month, k.scope
ORDER BY d.year, d.month, k.scope;
