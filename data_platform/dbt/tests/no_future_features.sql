select * from {{ ref('credit_features_asof') }}
where asof_date <> cast('{{ var("features_cutoff") }}' as date)
   or max_feature_event_date >= asof_date or max_feature_process_date >= asof_date
