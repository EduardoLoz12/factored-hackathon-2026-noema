select
    cast(date as DATE) as date,
    source_currency,
    target_currency,
    cast(exchange_rate as DOUBLE) as exchange_rate,
    cast(buy_rate as DOUBLE) as buy_rate,
    cast(sell_rate as DOUBLE) as sell_rate,
    source,
    _source_file,
    cast(_ingested_at as TIMESTAMP) as _ingested_at
from {{ input_parquet('validated/daily_exchange_rates/part.parquet') }}
