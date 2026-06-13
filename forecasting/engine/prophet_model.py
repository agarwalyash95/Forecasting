"""
Time-series demand forecasting using statsforecast (AutoARIMA + AutoETS).
Pure-Python, no C++ compiler required. Handles seasonality and trend natively.
Drop-in replacement for the Prophet model — same API surface.
"""
import os
import pickle
import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
# pyrefly: ignore [missing-import]
from django.conf import settings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

MODEL_DIR = Path(getattr(settings, 'ML_MODEL_DIR', Path(settings.BASE_DIR) / 'forecasting' / 'trained_models'))
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class AutoARIMADemandModel:
    """
    Per-product AutoARIMA + AutoETS ensemble demand model.
    Handles trend + seasonality with no compilation step.
    Provides forecast with confidence intervals via prediction intervals.
    """

    MIN_TRAINING_DAYS = 30

    def __init__(self, product_id: int):
        self.product_id = product_id
        self.model = None
        self.is_trained = False
        self.model_path = MODEL_DIR / f'autoarima_{product_id}.pkl'
        self._last_df = None  # Store last data for rolling predictions

    def train(self, df: pd.DataFrame) -> bool:
        """Train on DataFrame with columns [ds, y]."""
        if df is None or len(df) < self.MIN_TRAINING_DAYS:
            logger.warning(
                "Product %d: insufficient data (%d rows, need %d). Skipping AutoARIMA.",
                self.product_id, len(df) if df is not None else 0, self.MIN_TRAINING_DAYS
            )
            return False

        df = df[['ds', 'y']].copy()
        df['ds'] = pd.to_datetime(df['ds'])
        df['y'] = df['y'].clip(lower=0).fillna(0)
        df = df.sort_values('ds').drop_duplicates('ds')

        try:
            from statsforecast import StatsForecast
            from statsforecast.models import AutoARIMA, AutoETS, SeasonalNaive

            # Prepare input in Nixtla format (unique_id, ds, y)
            sf_df = df.copy()
            sf_df['unique_id'] = f'product_{self.product_id}'
            sf_df = sf_df.rename(columns={'ds': 'ds', 'y': 'y'})

            # Weekly seasonality (season_length=7) is appropriate for daily retail data
            models = [
                AutoARIMA(season_length=7),
                AutoETS(season_length=7),
                SeasonalNaive(season_length=7),  # Naive seasonal baseline
            ]

            self.model = StatsForecast(
                models=models,
                freq='D',
                n_jobs=1,
                verbose=False,
            )

            self.model.fit(sf_df[['unique_id', 'ds', 'y']])
            self._last_df = sf_df
            self.is_trained = True
            logger.info("AutoARIMA model trained for product %d on %d rows", self.product_id, len(df))
            return True

        except Exception as e:
            logger.error("AutoARIMA training failed for product %d: %s", self.product_id, e)
            return False

    def save(self):
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, 'wb') as f:
            pickle.dump({'model': self.model, 'last_df': self._last_df}, f)
        logger.info("AutoARIMA model saved: %s", self.model_path)

    def load(self) -> bool:
        if self.model_path.exists():
            try:
                with open(self.model_path, 'rb') as f:
                    data = pickle.load(f)
                self.model = data['model']
                self._last_df = data.get('last_df')
                self.is_trained = True
                return True
            except Exception as e:
                logger.error("Failed to load AutoARIMA model %s: %s", self.model_path, e)
        return False

    def predict(self, horizon_days: int = 30) -> list:
        """
        Generate forecast with 80% prediction intervals.
        Returns list of dicts: {date, predicted_demand, lower_bound, upper_bound}
        """
        if not self.is_trained and not self.load():
            return []

        try:
            # Forecast
            forecast_df = self.model.predict(h=horizon_days, level=[80])

            # Use AutoARIMA as primary, average with AutoETS if available
            results = []
            for _, row in forecast_df.iterrows():
                # Get the primary model forecast (AutoARIMA)
                yhat = row.get('AutoARIMA', row.get('AutoETS', row.get('SeasonalNaive', 0)))

                # Get prediction intervals
                lower_col = 'AutoARIMA-lo-80'
                upper_col = 'AutoARIMA-hi-80'
                lower = row.get(lower_col, yhat * 0.8)
                upper = row.get(upper_col, yhat * 1.2)

                # Ensemble: average all available model forecasts
                model_vals = []
                for col in ['AutoARIMA', 'AutoETS', 'SeasonalNaive']:
                    if col in row and not pd.isna(row[col]):
                        model_vals.append(max(0, row[col]))
                if model_vals:
                    yhat = sum(model_vals) / len(model_vals)

                results.append({
                    'date': row['ds'].strftime('%Y-%m-%d') if hasattr(row['ds'], 'strftime') else str(row['ds']),
                    'predicted_demand': max(0, round(float(yhat), 1)),
                    'lower_bound': max(0, round(float(lower), 1)),
                    'upper_bound': max(0, round(float(upper), 1)),
                    'model': 'autoarima_ets',
                })

            return results

        except Exception as e:
            logger.error("AutoARIMA prediction failed for product %d: %s", self.product_id, e)
            return []

    def get_chart_config(self, horizon_days: int = 30) -> dict:
        """Generate Chart.js-compatible config with confidence bands."""
        predictions = self.predict(horizon_days)
        if not predictions:
            return {}

        labels = [p['date'] for p in predictions]
        yhat   = [p['predicted_demand'] for p in predictions]
        lower  = [p['lower_bound'] for p in predictions]
        upper  = [p['upper_bound'] for p in predictions]

        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Predicted Demand',
                        'data': yhat,
                        'borderColor': '#6366f1',
                        'backgroundColor': 'rgba(99, 102, 241, 0.08)',
                        'borderWidth': 2.5,
                        'fill': False,
                        'tension': 0.4,
                        'pointRadius': 3,
                        'pointBackgroundColor': '#6366f1',
                    },
                    {
                        'label': 'Upper Bound (80%)',
                        'data': upper,
                        'borderColor': 'rgba(99,102,241,0.2)',
                        'backgroundColor': 'rgba(99,102,241,0.12)',
                        'borderWidth': 1,
                        'fill': '+1',
                        'pointRadius': 0,
                        'tension': 0.4,
                    },
                    {
                        'label': 'Lower Bound (80%)',
                        'data': lower,
                        'borderColor': 'rgba(99,102,241,0.2)',
                        'backgroundColor': 'rgba(99,102,241,0.0)',
                        'borderWidth': 1,
                        'fill': False,
                        'pointRadius': 0,
                        'tension': 0.4,
                    },
                ]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'legend': {'display': True, 'labels': {'color': '#94a3b8'}},
                    'title': {
                        'display': True,
                        'text': f'{horizon_days}-Day Demand Forecast (AutoARIMA+ETS)',
                        'color': '#f0f4ff',
                    },
                    'tooltip': {'mode': 'index', 'intersect': False}
                },
                'scales': {
                    'x': {
                        'display': True,
                        'ticks': {'color': '#64748b', 'maxTicksLimit': 10},
                        'grid': {'color': 'rgba(255,255,255,0.04)'}
                    },
                    'y': {
                        'display': True,
                        'beginAtZero': True,
                        'ticks': {'color': '#64748b'},
                        'grid': {'color': 'rgba(255,255,255,0.04)'},
                        'title': {'display': True, 'text': 'Units', 'color': '#64748b'}
                    }
                }
            }
        }


# ── Convenience alias (same API as old prophet_model) ─────────────────────────
ProphetDemandModel = AutoARIMADemandModel


def get_or_train_prophet(product) -> 'AutoARIMADemandModel':
    """Load or train an AutoARIMA model for a product (same API as before)."""
    from forecasting.engine.pipeline import load_product_sales_df

    pm = AutoARIMADemandModel(product.id)
    if not pm.load():
        df = load_product_sales_df(product.id, days=365)
        if not df.empty and pm.train(df):
            pm.save()
    return pm
