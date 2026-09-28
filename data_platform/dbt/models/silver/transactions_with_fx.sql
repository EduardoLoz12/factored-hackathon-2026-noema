select t.*,
       case when t.currency = 'USD' then 1.0 else fx.exchange_rate end as usd_rate,
       case when t.currency = 'USD' then t.amount
            else t.amount * fx.exchange_rate end as converted_amount_usd
from {{ ref('typed_transactions') }} t
left join {{ ref('stg_daily_exchange_rates') }} fx
  on fx.date = t.transaction_date
 and fx.source_currency = t.currency and fx.target_currency = 'USD'
