-- One row per campaign and per snapshot day, with the counters used by the KPIs.
select
    campaign_id,
    snapshot_date,
    sent,
    delivered,
    unique_views,
    clickers,
    unsubscriptions,
    hard_bounces,
    soft_bounces,
    complaints
from {{ source('brevo', 'fact_campaign_stats') }}
