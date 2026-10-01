import os
import joblib
import pandas as pd
import pytest

MODEL_PATH = 'data/models/churn_prediction_model.joblib'

def test_model_exists():
    """Check if the trained model file exists."""
    assert os.path.exists(MODEL_PATH), f"Model not found at {MODEL_PATH}. Run the training script first."

def test_model_prediction():
    """Test if the model pipeline can successfully predict on standard dummy data."""
    if not os.path.exists(MODEL_PATH):
        pytest.skip("Model not found. Skipping prediction test.")
        
    model = joblib.load(MODEL_PATH)
    
    dummy_data = pd.DataFrame({
        'segment': ['Premium'],
        'occupation': ['Engineer'],
        'marital_status': ['Single'],
        'education_level': ['Bachelors'],
        'credit_score': [720],
        'estimated_monthly_income': [5000.0],
        'product_count': [2],
        'total_balance_usd': [15000.0],
        'days_past_due': [0],
        'tenure_days': [365]
    })
    
    try:
        prediction = model.predict(dummy_data)
        assert len(prediction) == 1
        assert prediction[0] in [0, 1]
    except Exception as e:
        pytest.fail(f"Model prediction failed with error: {e}")
