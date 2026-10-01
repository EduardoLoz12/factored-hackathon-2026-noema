import os
import joblib
import duckdb
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

def train_churn_model():
    # Ensure models and model_cards directories exist
    os.makedirs('data/models', exist_ok=True)
    os.makedirs('ml/model_cards', exist_ok=True)
    
    print("Connecting to DuckDB...")
    con = duckdb.connect('data/noema.duckdb', read_only=True)
    
    print("Fetching data...")
    # Read from customer_360 table
    df = con.execute("SELECT * FROM noema_gold.customer_360").df()
    
    # Target variable formulation: create a binary 'target' from 'customer_status'
    # This assumes 'customer_status' has text indicating churn (e.g. 'Churned', 'Inactive')
    # If the column is already numeric, it passes through.
    if df['customer_status'].dtype == object:
        df['target'] = df['customer_status'].astype(str).str.lower().apply(
            lambda x: 1 if 'churn' in x or 'inactive' in x else 0
        )
    else:
        df['target'] = df['customer_status']
    
    # Define features
    categorical_features = ['segment', 'occupation', 'marital_status', 'education_level']
    numeric_features = ['credit_score', 'estimated_monthly_income', 'product_count', 
                        'total_balance_usd', 'days_past_due', 'tenure_days']
    
    # Drop rows with missing essential features
    df = df.dropna(subset=['target'] + numeric_features)
    
    X = df[categorical_features + numeric_features]
    y = df['target']
    
    print("Preprocessing and pipeline creation...")
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ]
    )
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(n_estimators=10, random_state=42)) # Reduced estimators for speed
    ])
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Training model...")
    pipeline.fit(X_train, y_train)
    
    print("Evaluating model...")
    y_pred = pipeline.predict(X_test)
    print(classification_report(y_test, y_pred))
    
    model_path = 'data/models/churn_prediction_model.joblib'
    print(f"Saving model to {model_path}...")
    joblib.dump(pipeline, model_path)
    print("Model training complete.")

if __name__ == "__main__":
    train_churn_model()
