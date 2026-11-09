-- Local vs national, avec une détection corrigée des campagnes locales.
SELECT CASE
         WHEN name LIKE 'LOCAL%'                THEN 'LOCAL'
         WHEN contains(name, '_STORE_')         THEN 'LOCAL'
         WHEN contains(lower(name), 'fermeture') THEN 'LOCAL'
         ELSE 'NATIONAL'
       END AS type_campagne,
       COUNT(*) AS campagnes,
       SUM(CASE WHEN unsub_rate_pct > click_rate_pct THEN 1 ELSE 0 END) AS plus_de_desinscrits_que_de_clics,
       ROUND(AVG(click_rate_pct), 2) AS clics_pct,
       ROUND(AVG(unsub_rate_pct), 3) AS desinscriptions_pct
FROM v_campaign_kpis
GROUP BY type_campagne;