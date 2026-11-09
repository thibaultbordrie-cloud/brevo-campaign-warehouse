-- Brevo counts a click as an open, so clickers should not exceed unique openers.
-- Severity "warn": a few exceptions can come from tracking, they are reported but do not fail the build.
{{ config(severity = 'warn') }}
select campaign_id, snapshot_date, unique_views, clickers
from {{ ref('stg_campaign_snapshots') }}
where clickers > unique_views
