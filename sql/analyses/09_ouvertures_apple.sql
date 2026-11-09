-- Apple Mail Privacy Protection: are automatic Apple opens inflating the open rate?
-- Check: Brevo's uniqueViews equals trackableViews (unique opens without Apple's automatic opens),
-- so the open rate in v_campaign_kpis already excludes them. appleMppOpens is a separate count of
-- automatic opens (not unique people), shown here per 100 delivered emails for scale only.
SELECT k.scope,
       COUNT(*)                                                                     AS campaigns,
       ROUND(100.0 * SUM(f.unique_views)    / NULLIF(SUM(f.delivered), 0), 2)       AS open_rate_pct,
       ROUND(100.0 * SUM(f.trackable_views) / NULLIF(SUM(f.delivered), 0), 2)       AS open_rate_without_apple_pct,
       SUM(f.unique_views) = SUM(f.trackable_views)                                 AS open_rate_already_excludes_apple,
       ROUND(100.0 * SUM(f.apple_mpp_opens) / NULLIF(SUM(f.delivered), 0), 2)       AS apple_auto_opens_per_100_delivered
FROM v_campaign_kpis k
JOIN fact_campaign_stats f ON f.campaign_id = k.campaign_id AND f.snapshot_date = k.snapshot_date
GROUP BY k.scope;
