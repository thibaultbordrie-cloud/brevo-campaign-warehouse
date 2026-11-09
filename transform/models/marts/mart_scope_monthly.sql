-- Local vs national, month by month (the main finding of the project).
select
    {{ dbt.date_trunc('month', 'send_date') }}              as send_month,
    scope,
    count(*)                                             as campaigns,
    sum(delivered)                                       as delivered,
    round(avg(click_rate_pct), 2)                        as avg_click_rate_pct,
    round(avg(unsub_rate_pct), 3)                        as avg_unsub_rate_pct,
    sum(case when more_unsubscribed_than_clickers then 1 else 0 end) as campaigns_losing_more_than_clicking
from {{ ref('mart_campaign_kpis') }}
where send_date is not null
group by 1, 2
