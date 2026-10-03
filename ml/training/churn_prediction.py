import json
import os

import duckdb
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def train_churn_model():
    os.makedirs("data/models", exist_ok=True)
    os.makedirs("ml/model_cards", exist_ok=True)

    con = duckdb.connect("data/noema.duckdb", read_only=True)

    # Extract data with basic conversion to avoid country discrepancies (simulating Eduardo's fix)
    df = con.execute("""
        SELECT
            customer_status,
            segment,
            occupation,
            marital_status,
            education_level,
            credit_score,
            total_balance_usd,
            COALESCE(days_past_due, 0) AS days_past_due,
            tenure_days,
            product_count,
            CASE
                WHEN country = 'Colombia' THEN estimated_monthly_income / 3900.0
                WHEN country = 'Argentina' THEN estimated_monthly_income / 350.0
                WHEN country = 'México' THEN estimated_monthly_income / 17.0
                ELSE estimated_monthly_income
            END AS estimated_monthly_income_usd
        FROM noema_gold.customer_360
    """).df()

    # Fix Target Formulation
    df["target"] = df["customer_status"].isin(["Closed", "Suspended", "Inactive"]).astype(int)

    categorical_features = ["segment", "occupation", "marital_status", "education_level"]
    numeric_features = [
        "credit_score",
        "estimated_monthly_income_usd",
        "product_count",
        "total_balance_usd",
        "days_past_due",
        "tenure_days",
    ]

    # Drop rows only if features are missing, not the structural nulls we just filled
    df = df.dropna(subset=categorical_features + numeric_features)

    X = df[categorical_features + numeric_features]
    y = df["target"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced"),
            ),
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    print(classification_report(y_test, y_pred))

    model_path = "data/models/churn_prediction_model.joblib"
    joblib.dump(pipeline, model_path)

    report = {
        "model_name": "Customer Churn Prediction Model (V2 - Fixed)",
        "version": "2.0",
        "task": "Classification",
        "description": (
            "Predicts whether a customer is likely to churn. "
            "Fixed target leakage and structural nulls."
        ),
        "target_variable": "customer_status in ('Closed', 'Suspended', 'Inactive')",
        "features": categorical_features + numeric_features,
        "model_type": "RandomForestClassifier(class_weight='balanced')",
        "metrics": {"Accuracy": acc, "Precision": prec, "Recall": rec, "F1-Score": f1},
        "author": "Antigravity (Post-Audit)",
    }

    with open("ml/model_cards/churn_prediction.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    train_churn_model()
