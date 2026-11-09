-- A campaign cannot deliver more emails than it sent. Returns the faulty rows (none = test passes).
select campaign_id, snapshot_date, sent, delivered
from {{ ref('stg_campaign_snapshots') }}
where delivered > sent
