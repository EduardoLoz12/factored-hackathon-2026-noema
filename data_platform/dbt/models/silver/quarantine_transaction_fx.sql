select *, 'missing_operation_date_fx' as _rejection_reason
from {{ ref('transactions_with_fx') }} where usd_rate is null
