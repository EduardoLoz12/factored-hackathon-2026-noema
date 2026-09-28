select 1 as failure where
(select count(*) from {{ ref('typed_transactions') }}) <>
(select count(*) from {{ ref('stg_transactions') }}) +
(select count(*) from {{ ref('quarantine_transaction_fx') }})
