-- Monthly trend: volume sent and average KPIs per month of sending.
SELECT d.year, d.month,
       COUNT(*)                          AS campaigns,
       SUM(k.delivered)                  AS delivered,
       ROUND(AVG(k.open_rate_pct), 2)    AS avg_open_rate_pct,
       ROUND(AVG(k.click_rate_pct), 2)   AS avg_click_rate_pct,
       ROUND(AVG(k.unsub_rate_pct), 3)   AS avg_unsub_rate_pct
FROM v_campaign_kpis k
JOIN dim_date d ON d.full_date = k.send_date
GROUP BY d.year, d.month
ORDER BY d.year, d.month;
