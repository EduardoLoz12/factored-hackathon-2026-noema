select customer_id, asof_date from {{ ref('credit_features_asof') }}
group by customer_id, asof_date having count(*)<>1
