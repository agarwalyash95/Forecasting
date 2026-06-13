"""
RandomForest-based demand forecasting model (fallback for products with < 2 years of data).
"""
import os
import joblib
import numpy as np
import logging
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_DIR = Path(getattr(settings, 'ML_MODEL_DIR', Path(settings.BASE_DIR) / 'forecasting' / 'trained_models'))
MODEL_PATH = MODEL_DIR / 'rf_demand_model.joblib'


class RandomForestDemandModel:
    def __init__(self):
        from sklearn.ensemble import RandomForestRegressor
        self.model = RandomForestRegressor(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        self.is_trained = False
        self.feature_importances_ = None

    def train(self, X: np.ndarray, y: np.ndarray) -> bool:
        if len(X) < 10:
            logger.warning("Insufficient data for RandomForest training (%d samples)", len(X))
            return False
        self.model.fit(X, y)
        self.is_trained = True
        self.feature_importances_ = self.model.feature_importances_
        logger.info("RandomForest trained on %d samples", len(X))
        return True

    def save(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, MODEL_PATH)
        logger.info("RandomForest model saved to %s", MODEL_PATH)

    def load(self) -> bool:
        if MODEL_PATH.exists():
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            logger.info("RandomForest model loaded from %s", MODEL_PATH)
            return True
        return False

    def predict_future(self, product, horizon_days: int = 30) -> list:
        """Predict future demand for a product using RF model."""
        if not self.is_trained and not self.load():
            return []

        from forecasting.engine.pipeline import load_product_sales_df, preprocess_sales_df
        import pandas as pd

        df = load_product_sales_df(product.id, days=90)
        if df.empty:
            return []

        df = preprocess_sales_df(df)
        today = datetime.now().date()
        future_dates = [today + timedelta(days=i) for i in range(1, horizon_days + 1)]

        # Use last known rolling averages
        rolling_7d  = df['rolling_7d'].iloc[-1] if len(df) > 0 else 0
        rolling_14d = df['rolling_14d'].iloc[-1] if len(df) > 0 else 0
        rolling_30d = df['rolling_30d'].iloc[-1] if len(df) > 0 else 0
        lag_1 = df['y'].iloc[-1] if len(df) > 0 else 0
        lag_7 = df['y'].iloc[-7] if len(df) >= 7 else 0

        try:
            import holidays as holidays_lib
            india_holidays = holidays_lib.India(years=list(set(d.year for d in future_dates)))
        except Exception:
            india_holidays = {}

        X_pred = []
        for d in future_dates:
            X_pred.append([
                d.weekday(),
                d.month,
                1 if d.weekday() >= 5 else 0,
                d.isocalendar()[1],
                rolling_7d, rolling_14d, rolling_30d,
                lag_1, lag_7,
                1 if d in india_holidays else 0,
                float(product.price),
                product.category.id if product.category else 0
            ])

        predictions = self.model.predict(np.array(X_pred))
        return [
            {
                'date': future_dates[i].strftime('%Y-%m-%d'),
                'predicted_demand': max(0, round(float(p), 1)),
            }
            for i, p in enumerate(predictions)
        ]


# Singleton
rf_model = RandomForestDemandModel()
