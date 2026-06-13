"""
Pandas-based data preprocessing pipeline for the forecasting engine.
Handles imputation, normalization, and feature engineering.
"""
import pandas as pd
import numpy as np
import logging
from datetime import date, timedelta

try:
    import holidays as holidays_lib
    HOLIDAYS_AVAILABLE = True
except ImportError:
    HOLIDAYS_AVAILABLE = False

logger = logging.getLogger(__name__)


def load_product_sales_df(product_id: int, days: int = 365) -> pd.DataFrame:
    """Load sales records for a product from MySQL into a pandas DataFrame."""
    from forecasting.models import SalesRecord
    from django.utils import timezone

    start_date = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(
        product_id=product_id,
        date__gte=start_date
    ).values('date', 'quantity', 'revenue').order_by('date')

    if not records:
        return pd.DataFrame(columns=['ds', 'y', 'revenue'])

    df = pd.DataFrame(list(records))
    df.rename(columns={'date': 'ds', 'quantity': 'y'}, inplace=True)
    df['ds'] = pd.to_datetime(df['ds'])
    df = df.groupby('ds').agg({'y': 'sum', 'revenue': 'sum'}).reset_index()
    return df


def preprocess_sales_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full preprocessing pipeline:
    1. Resample to daily frequency (fill gaps)
    2. Missing value imputation (zero for true gaps, ffill for short gaps)
    3. Remove negatives
    4. Add rolling averages and lag features
    5. Add holiday flags
    """
    if df.empty or 'ds' not in df.columns:
        return df

    df = df.copy()
    df['ds'] = pd.to_datetime(df['ds'])
    df = df.sort_values('ds').drop_duplicates(subset='ds')

    # Fill date gaps with daily resampling
    df = df.set_index('ds').resample('D').sum()

    # Impute: short gaps (<=3 days) use forward fill, long gaps use 0
    df['y'] = df['y'].replace(0, np.nan)
    df['y'] = df['y'].fillna(method='ffill', limit=3)
    df['y'] = df['y'].fillna(0)
    df['y'] = df['y'].clip(lower=0)

    df = df.reset_index()
    df.rename(columns={'index': 'ds'}, inplace=True)
    if 'ds' not in df.columns:
        df = df.reset_index()

    # ── Rolling averages ──────────────────────────────────────────────────────
    df['rolling_7d']  = df['y'].rolling(7,  min_periods=1).mean()
    df['rolling_14d'] = df['y'].rolling(14, min_periods=1).mean()
    df['rolling_30d'] = df['y'].rolling(30, min_periods=1).mean()

    # ── Lag features ─────────────────────────────────────────────────────────
    df['lag_1'] = df['y'].shift(1).fillna(0)
    df['lag_7'] = df['y'].shift(7).fillna(0)

    # ── Calendar features ─────────────────────────────────────────────────────
    df['day_of_week'] = df['ds'].dt.dayofweek
    df['month']       = df['ds'].dt.month
    df['is_weekend']  = (df['ds'].dt.dayofweek >= 5).astype(int)
    df['week_of_year'] = df['ds'].dt.isocalendar().week.astype(int)

    # ── Holiday flags (India) ────────────────────────────────────────────────
    if HOLIDAYS_AVAILABLE:
        try:
            years = df['ds'].dt.year.unique().tolist()
            india_holidays = holidays_lib.India(years=years)
            df['is_holiday'] = df['ds'].dt.date.apply(lambda d: 1 if d in india_holidays else 0)
        except Exception:
            df['is_holiday'] = 0
    else:
        df['is_holiday'] = 0

    return df


def build_rf_feature_matrix(df: pd.DataFrame, price: float = 0.0, category_id: int = 0) -> tuple:
    """
    Extract feature matrix X and target y for RandomForest training.
    Returns (X: np.ndarray, y: np.ndarray)
    """
    df = preprocess_sales_df(df)

    feature_cols = [
        'day_of_week', 'month', 'is_weekend', 'week_of_year',
        'rolling_7d', 'rolling_14d', 'rolling_30d',
        'lag_1', 'lag_7', 'is_holiday'
    ]

    # Add static product features
    df['price']       = float(price)
    df['category_id'] = int(category_id)
    feature_cols += ['price', 'category_id']

    # Drop rows where lag features are NaN (first few rows)
    df_clean = df.dropna(subset=feature_cols)

    X = df_clean[feature_cols].values
    y = df_clean['y'].values
    return X, y
