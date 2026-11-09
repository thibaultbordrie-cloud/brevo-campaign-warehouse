{% test unique_combination(model, columns) %}
-- Same idea as dbt_utils.unique_combination_of_columns, written here to avoid installing a package.
select {{ columns | join(', ') }}, count(*) as occurrences
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
