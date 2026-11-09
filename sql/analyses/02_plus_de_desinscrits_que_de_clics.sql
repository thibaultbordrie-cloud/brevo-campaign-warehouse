-- Campaigns that lost more subscribers than they got clickers.
SELECT c.name, k.send_date, f.clickers, f.unsubscriptions
FROM v_campaign_kpis k
JOIN dim_campaign c USING (campaign_id)
JOIN fact_campaign_stats f ON f.campaign_id = k.campaign_id AND f.snapshot_date = k.snapshot_date
WHERE f.unsubscriptions > f.clickers
ORDER BY k.send_date DESC;
