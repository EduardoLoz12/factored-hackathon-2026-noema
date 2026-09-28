{% macro input_parquet(relative) -%}
  {% if target.type == 'databricks' %}
    parquet.`{{ env_var('NOEMA_VOLUME') }}/{{ relative }}`
  {% else %}
    read_parquet('{{ env_var("NOEMA_DATA_DIR", "../../data") }}/{{ relative }}', hive_partitioning=false)
  {% endif %}
{%- endmacro %}

{% macro days_between(start, finish) -%}
  {% if target.type == 'databricks' %}datediff({{ finish }}, {{ start }})
  {% else %}date_diff('day', {{ start }}, {{ finish }}){% endif %}
{%- endmacro %}

{% macro product_list(column) -%}
  {% if target.type == 'databricks' %}concat_ws(', ', sort_array(collect_set({{ column }})))
  {% else %}string_agg(distinct {{ column }}, ', ' order by {{ column }}){% endif %}
{%- endmacro %}
