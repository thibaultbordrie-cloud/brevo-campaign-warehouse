-- Deliverability: the 10 campaigns with the highest bounce rate, with spam complaints.
SELECT k.name, k.send_date, f.sent,
       ROUND(100.0 * f.hard_bounces / NULLIF(f.sent, 0), 3) AS hard_bounce_pct,
       ROUND(100.0 * f.soft_bounces / NULLIF(f.sent, 0), 3) AS soft_bounce_pct,
       f.complaints
FROM v_campaign_kpis k
JOIN fact_campaign_stats f ON f.campaign_id = k.campaign_id AND f.snapshot_date = k.snapshot_date
WHERE f.sent >= 1000
ORDER BY (f.hard_bounces + f.soft_bounces) * 1.0 / f.sent DESC
LIMIT 10;
