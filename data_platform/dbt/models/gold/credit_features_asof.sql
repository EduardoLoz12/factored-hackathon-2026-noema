-- No se incorpora el snapshot de productos ni el score actual.
with eligible_customers as (
    select customer_id, registration_date from {{ ref('stg_customers') }}
    where registration_date < cast('{{ var("features_cutoff") }}' as date)
), historical as (
    select t.* from {{ ref('stg_transactions') }} t
    where transaction_date < cast('{{ var("features_cutoff") }}' as date)
      and process_date < cast('{{ var("features_cutoff") }}' as date)
      and transaction_date >= cast('{{ var("features_cutoff") }}' as date) - interval '180' day
      and transaction_status = 'Approved'
), aggregates as (
    select customer_id, count(*) as transaction_count_180d,
           sum(abs(amount_usd)) as transaction_volume_usd_180d,
           sum(case when transaction_type = 'Depósito' then abs(amount_usd) else 0 end) as deposits_usd_180d,
           sum(case when transaction_type in ('Pago','Compra','Retiro') then abs(amount_usd) else 0 end) as outflows_usd_180d,
           sum(case when transaction_type in ('Transferencia','Ajuste') then 1 else 0 end) as ambiguous_transactions_180d,
           count(distinct date_trunc('month', transaction_date)) as active_months_180d,
           max(transaction_date) as max_feature_event_date,
           max(process_date) as max_feature_process_date
    from historical group by customer_id
)
select c.customer_id, cast('{{ var("features_cutoff") }}' as date) as asof_date,
       {{ days_between('c.registration_date', "cast('" ~ var('features_cutoff') ~ "' as date)") }} as tenure_days,
       coalesce(a.transaction_count_180d,0) as transaction_count_180d,
       coalesce(a.transaction_volume_usd_180d,0) as transaction_volume_usd_180d,
       coalesce(a.deposits_usd_180d,0) as deposits_usd_180d,
       coalesce(a.outflows_usd_180d,0) as outflows_usd_180d,
       coalesce(a.ambiguous_transactions_180d,0) as ambiguous_transactions_180d,
       coalesce(a.active_months_180d,0) as active_months_180d,
       a.max_feature_event_date, a.max_feature_process_date
from eligible_customers c left join aggregates a using(customer_id)
