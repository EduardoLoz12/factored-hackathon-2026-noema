# Customer Churn Prediction Model

## Overview
The Customer Churn Prediction model predicts the likelihood of a customer leaving the business or becoming inactive. It is trained on demographic, financial, and product engagement metrics sourced from the customer golden record table (`noema_gold.customer_360`).

## Data Source
- **Database:** `data/noema.duckdb`
- **Table:** `noema_gold.customer_360`
- **Target Variable:** `customer_status` (Dynamically mapped to a binary label: 1 = Churned/Inactive, 0 = Active).

## Features
The model analyzes the following features to determine churn likelihood:
- **Demographics:** `occupation`, `marital_status`, `education_level`
- **Financial Profile:** `credit_score`, `estimated_monthly_income`, `total_balance_usd`
- **Engagement / Health:** `segment`, `product_count`, `days_past_due`, `tenure_days`

## Model Architecture
- **Data Preprocessing:**
  - Numeric features are scaled using Scikit-Learn's `StandardScaler`.
  - Categorical features are one-hot encoded using `OneHotEncoder`. Out-of-vocabulary instances are ignored to prevent runtime inference errors.
- **Algorithm:** The model is a `RandomForestClassifier`.

## Repository Artifacts
- **Training Script:** `ml/training/churn_prediction.py`
- **Model Card:** `ml/model_cards/churn_prediction.json`
- **Trained Artifact:** `data/models/churn_prediction_model.joblib`
- **Unit Tests:** `tests/ml/test_churn_prediction.py`
