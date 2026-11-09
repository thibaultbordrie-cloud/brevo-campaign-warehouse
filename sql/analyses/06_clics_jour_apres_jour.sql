-- How clicks keep arriving after the send: one line per campaign and per snapshot day.
-- Meaningful once the daily ingestion has run for a few days.
SELECT c.name,
       CAST(c.sent_at AS DATE)                        AS send_date,
       f.snapshot_date,
       f.snapshot_date - CAST(c.sent_at AS DATE)      AS days_after_send,
       f.clickers,
       f.clickers - LAG(f.clickers) OVER (PARTITION BY f.campaign_id ORDER BY f.snapshot_date) AS new_clickers
FROM fact_campaign_stats f
JOIN dim_campaign c USING (campaign_id)
WHERE c.sent_at >= CURRENT_DATE - INTERVAL 14 DAY
ORDER BY c.sent_at DESC, f.snapshot_date;
