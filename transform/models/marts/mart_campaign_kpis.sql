-- One row per campaign with its KPIs. Same formulas as docs/KPI.md.
select
    c.campaign_id,
    c.campaign_name,
    c.scope,
    c.send_date,
    s.snapshot_date,
    s.delivered,
    round(100.0 * s.unique_views    / nullif(s.delivered, 0), 2)    as open_rate_pct,
    round(100.0 * s.clickers        / nullif(s.delivered, 0), 2)    as click_rate_pct,
    round(100.0 * s.clickers        / nullif(s.unique_views, 0), 2) as ctor_pct,
    round(100.0 * s.unsubscriptions / nullif(s.delivered, 0), 3)    as unsub_rate_pct,
    s.unsubscriptions > s.clickers                                   as more_unsubscribed_than_clickers
from {{ ref('stg_campaigns') }} c
join {{ ref('int_campaign_latest_snapshot') }} s using (campaign_id)
