-- Keeps only the most recent snapshot of each campaign: its final statistics so far.
select *
from {{ ref('stg_campaign_snapshots') }}
where true   -- BigQuery accepts QUALIFY only after a WHERE, GROUP BY or HAVING
qualify row_number() over (partition by campaign_id order by snapshot_date desc) = 1
