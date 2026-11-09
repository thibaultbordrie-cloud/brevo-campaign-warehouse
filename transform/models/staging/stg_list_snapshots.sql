select
    list_id,
    snapshot_date,
    -- Brevo leaves totalSubscribers at 0 for this account: fall back to unique subscribers
    case when total_subscribers > 0 then total_subscribers else unique_subscribers end as subscribers,
    total_subscribers,
    total_blacklisted
from {{ source('brevo', 'fact_list_size') }}
