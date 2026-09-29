select
    campaign_id,
    campaign_name,
    description,
    campaign_type,
    campaign_objective,
    promoted_product,
    target_segment,
    target_country,
    cast(start_date as DATE) as start_date,
    cast(end_date as DATE) as end_date,
    cast(budget as DOUBLE) as budget,
    campaign_status,
    cast(expected_conversion_rate as DOUBLE) as expected_conversion_rate,
    _source_file,
    cast(_ingested_at as TIMESTAMP) as _ingested_at
from {{ input_parquet('validated/marketing_campaigns/part.parquet') }}
