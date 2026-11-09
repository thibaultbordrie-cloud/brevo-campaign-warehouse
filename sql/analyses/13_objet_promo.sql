-- Subjects announcing a discount (a "%" sign) vs the others.
SELECT CASE WHEN contains(c.subject, '%') THEN 'discount in subject' ELSE 'no discount in subject' END AS subject_type,
       COUNT(*)                           AS campaigns,
       ROUND(AVG(k.open_rate_pct), 2)     AS avg_open_rate_pct,
       ROUND(AVG(k.click_rate_pct), 2)    AS avg_click_rate_pct,
       ROUND(AVG(k.unsub_rate_pct), 3)    AS avg_unsub_rate_pct
FROM v_campaign_kpis k
JOIN dim_campaign c USING (campaign_id)
WHERE c.subject IS NOT NULL
GROUP BY subject_type;
