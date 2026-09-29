-- Catálogo observado. No existe una política de oferta en el dataset.
-- Condiciones desconocidas deben detener la decisión, no convertirse en defaults.
select distinct product_type, currency,
       cast(null as integer) as minimum_credit_score,
       cast(null as double) as minimum_amount,
       cast(null as double) as maximum_amount,
       cast(null as integer) as minimum_term_months,
       cast(null as integer) as maximum_term_months,
       cast(null as double) as annual_interest_rate,
       'pending_team_policy' as policy_version,
       false as policy_ready
from {{ ref('stg_products') }}
where product_type in ('Tarjeta Crédito','Préstamo Personal','Préstamo Hipotecario')
