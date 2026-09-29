with valuation_date as (select max(date) as date from {{ ref('stg_daily_exchange_rates') }}),
products as (
    select p.*, case when p.currency = 'USD' then p.current_balance
                     else p.current_balance * fx.exchange_rate end as balance_usd
    from {{ ref('stg_products') }} p cross join valuation_date d
    left join {{ ref('stg_daily_exchange_rates') }} fx
      on fx.date=d.date and fx.source_currency=p.currency and fx.target_currency='USD'
), grouped as (
    select customer_id, count(*) as product_count,
           {{ product_list('product_type') }} as product_types,
           case when count(balance_usd)=count(*) then sum(balance_usd) end as total_balance_usd,
           sum(case when balance_usd is null then 1 else 0 end) as unvalued_products,
           max(days_past_due) as days_past_due
    from products group by customer_id
)
select c.*, coalesce(p.product_count,0) as product_count, p.product_types,
       case when p.product_count is null then 0 else p.total_balance_usd end as total_balance_usd,
       coalesce(p.unvalued_products,0) as unvalued_products, p.days_past_due,
       {{ days_between('c.registration_date', 'd.date') }} as tenure_days,
       d.date as valuation_date
from {{ ref('stg_customers') }} c cross join valuation_date d
left join grouped p using(customer_id)
