select transaction_id from {{ ref('stg_transactions') }}
where amount_usd is null or abs(amount_usd - amount * usd_rate)>0.000001
