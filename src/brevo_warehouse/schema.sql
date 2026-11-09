-- Star schema for Brevo email campaigns.
-- raw_*  : what the API returned, unchanged (lets us rebuild everything).
-- dim_*  : descriptive tables.
-- fact_* : numbers, one row per campaign and per snapshot day (history of statistics).

CREATE TABLE IF NOT EXISTS raw_email_campaigns (
    campaign_id   BIGINT,
    ingested_at   TIMESTAMP,
    payload       JSON
);

CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_id   BIGINT PRIMARY KEY,
    name          VARCHAR,
    subject       VARCHAR,
    campaign_type VARCHAR,
    tag           VARCHAR,
    status        VARCHAR,
    created_at    TIMESTAMP,
    sent_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key   INTEGER PRIMARY KEY,   -- YYYYMMDD
    full_date  DATE,
    year       INTEGER,
    month      INTEGER,
    day        INTEGER,
    iso_week   INTEGER,
    weekday    INTEGER                 -- 1 = Monday ... 7 = Sunday
);

CREATE TABLE IF NOT EXISTS fact_campaign_stats (
    campaign_id      BIGINT,
    snapshot_date    DATE,             -- day the statistics were read
    send_date_key    INTEGER,          -- day the campaign was sent
    sent             BIGINT,
    delivered        BIGINT,
    unique_views     BIGINT,
    trackable_views  BIGINT,
    apple_mpp_opens  BIGINT,
    unique_clicks    BIGINT,
    clickers         BIGINT,
    unsubscriptions  BIGINT,
    hard_bounces     BIGINT,
    soft_bounces     BIGINT,
    complaints       BIGINT,
    PRIMARY KEY (campaign_id, snapshot_date)
);

-- Contact lists: one row per list (descriptive) ...
CREATE TABLE IF NOT EXISTS dim_list (
    list_id    BIGINT PRIMARY KEY,
    name       VARCHAR,
    folder_id  BIGINT
);

-- ... and its size, one row per list and per snapshot day.
CREATE TABLE IF NOT EXISTS fact_list_size (
    list_id             BIGINT,
    snapshot_date       DATE,
    total_subscribers   BIGINT,
    unique_subscribers  BIGINT,
    total_blacklisted   BIGINT,
    PRIMARY KEY (list_id, snapshot_date)
);

-- One definition per KPI (see docs/KPI.md). Latest snapshot of each campaign only.
CREATE OR REPLACE VIEW v_campaign_kpis AS
WITH latest AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY snapshot_date DESC) AS rn
    FROM fact_campaign_stats
)
SELECT
    c.campaign_id,
    c.name,
    c.tag,
    -- Scope rule, defined once: local store operations do not always carry the LOCAL_ prefix.
    CASE
        WHEN c.name LIKE 'LOCAL%'                 THEN 'LOCAL'
        WHEN contains(c.name, '_STORE_')          THEN 'LOCAL'
        WHEN contains(lower(c.name), 'fermeture') THEN 'LOCAL'
        ELSE 'NATIONAL'
    END                                                      AS scope,
    d.full_date                                              AS send_date,
    l.sent,
    l.delivered,
    ROUND(100.0 * l.unique_views    / NULLIF(l.delivered, 0), 2)  AS open_rate_pct,
    ROUND(100.0 * l.clickers        / NULLIF(l.delivered, 0), 2)  AS click_rate_pct,
    ROUND(100.0 * l.clickers        / NULLIF(l.unique_views, 0), 2) AS ctor_pct,
    ROUND(100.0 * l.unsubscriptions / NULLIF(l.delivered, 0), 3)  AS unsub_rate_pct,
    l.snapshot_date
FROM latest l
JOIN dim_campaign c USING (campaign_id)
LEFT JOIN dim_date d ON d.date_key = l.send_date_key
WHERE l.rn = 1;

-- Subscribers of a list, defined once. Brevo's API leaves totalSubscribers at 0 for this account
-- (seen 22/10/2026: 0 on every list, uniqueSubscribers filled), so the count falls back to
-- uniqueSubscribers when the total is empty.
CREATE OR REPLACE VIEW v_list_size AS
SELECT
    f.list_id,
    f.snapshot_date,
    CASE WHEN f.total_subscribers > 0 THEN f.total_subscribers ELSE f.unique_subscribers END AS subscribers,
    f.total_subscribers,
    f.unique_subscribers,
    f.total_blacklisted
FROM fact_list_size f;

-- Day-to-day change of each list size (first snapshot of a list has no change).
CREATE OR REPLACE VIEW v_list_growth AS
SELECT
    s.list_id,
    l.name,
    s.snapshot_date,
    s.subscribers,
    s.subscribers - LAG(s.subscribers) OVER w              AS change_subscribers,
    s.total_blacklisted,
    s.total_blacklisted - LAG(s.total_blacklisted) OVER w  AS change_blacklisted
FROM v_list_size s
JOIN dim_list l USING (list_id)
WINDOW w AS (PARTITION BY s.list_id ORDER BY s.snapshot_date);
