-- Sin FX de la fecha exacta, la fila pasa a cuarentena: nunca se rellena con futuro.
select transaction_id, transaction_date, process_date, product_id, customer_id,
       transaction_type, transaction_category, amount, currency,
       converted_amount_usd as amount_usd, amount_usd as reported_amount_usd,
       channel, branch_id, merchant_name, merchant_category, transaction_country,
       transaction_city, transaction_status, response_code, is_fraud, fraud_score,
       latitude, longitude, usd_rate, _source_file, _ingested_at
from {{ ref('transactions_with_fx') }}
where usd_rate is not null
