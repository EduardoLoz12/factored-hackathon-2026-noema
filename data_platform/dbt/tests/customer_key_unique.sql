select customer_id from {{ ref('customer_360') }}
group by customer_id having count(*)<>1
