-- Top 10 campaigns by CTOR (clickers / openers), among campaigns delivered to at least 1,000 contacts.
SELECT name, scope, send_date, delivered, open_rate_pct, ctor_pct
FROM v_campaign_kpis
WHERE delivered >= 1000
ORDER BY ctor_pct DESC
LIMIT 10;
