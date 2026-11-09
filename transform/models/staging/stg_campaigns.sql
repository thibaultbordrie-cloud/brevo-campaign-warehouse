-- One row per campaign: clean names, send date, and the local / national scope rule.
-- Portable SQL: the same model runs on DuckDB (local) and BigQuery (cloud).
select
    campaign_id,
    trim(name)                         as campaign_name,
    subject,
    tag,
    cast(sent_at as date)              as send_date,
    sent_at,
    case
        when name like 'LOCAL%'                 then 'LOCAL'
        when strpos(name, '_STORE_') > 0           then 'LOCAL'
        when strpos(lower(name), 'fermeture') > 0 then 'LOCAL'
        else 'NATIONAL'
    end                                as scope
from {{ source('brevo', 'dim_campaign') }}
