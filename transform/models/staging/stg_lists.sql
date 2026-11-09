select
    list_id,
    trim(name) as list_name,
    folder_id
from {{ source('brevo', 'dim_list') }}
