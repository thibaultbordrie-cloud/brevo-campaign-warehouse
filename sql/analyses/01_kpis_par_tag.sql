-- Compare les campagnes locales et nationales, sur tout l'historique.
SELECT CASE WHEN name LIKE 'LOCAL%' THEN 'LOCAL' ELSE 'NATIONAL' END AS type_campagne,
       COUNT(*)                         AS campaigns,
       SUM(delivered)                   AS delivered,
       ROUND(AVG(open_rate_pct), 2)     AS avg_open_rate_pct,
       ROUND(AVG(click_rate_pct), 2)    AS avg_click_rate_pct,
       ROUND(AVG(unsub_rate_pct), 3)    AS avg_unsub_rate_pct
FROM v_campaign_kpis
GROUP BY type_campagne
ORDER BY delivered DESC;