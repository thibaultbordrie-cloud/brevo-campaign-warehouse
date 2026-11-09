-- Day-to-day change of each contact list.
select
    s.list_id,
    l.list_name,
    s.snapshot_date,
    s.subscribers,
    s.subscribers - lag(s.subscribers) over w as change_subscribers,
    s.total_blacklisted,
    s.total_blacklisted - lag(s.total_blacklisted) over w as change_blacklisted
from {{ ref('stg_list_snapshots') }} s
join {{ ref('stg_lists') }} l using (list_id)
window w as (partition by s.list_id order by s.snapshot_date)
