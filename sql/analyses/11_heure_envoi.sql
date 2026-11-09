-- Does the hour of sending matter? Average KPIs per hour (local time of the send).
SELECT EXTRACT(hour FROM c.sent_at)       AS send_hour,
       COUNT(*)                           AS campaigns,
       ROUND(AVG(k.open_rate_pct), 2)     AS avg_open_rate_pct,
       ROUND(AVG(k.click_rate_pct), 2)    AS avg_click_rate_pct
FROM v_campaign_kpis k
JOIN dim_campaign c USING (campaign_id)
WHERE c.sent_at IS NOT NULL
GROUP BY send_hour
ORDER BY send_hour;
