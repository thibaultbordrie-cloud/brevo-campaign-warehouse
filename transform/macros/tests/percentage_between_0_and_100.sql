{% test percentage_between_0_and_100(model, column_name) %}
-- Fails for every row where a percentage is outside 0..100 (empty values are allowed).
select *
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < 0 or {{ column_name }} > 100)
{% endtest %}
