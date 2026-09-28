select * from {{ input_parquet('quality/dq_report.parquet') }}
union all
select 'transactions' as table_name, 'missing_operation_date_fx' as metric,
       'currency' as column_name, cast(count(*) as double) as value
from {{ ref('quarantine_transaction_fx') }}
