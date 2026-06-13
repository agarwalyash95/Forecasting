"""
Query functions used by chatbot tools and API views.
"""
import json
import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum, Avg, Count, F, Q

from forecasting.models import Product, SalesRecord, StockAlert, InventoryLog

logger = logging.getLogger(__name__)


# ─── KPIs ─────────────────────────────────────────────────────────────────────

def get_summary_kpis(days: int = 30) -> dict:
    start = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(date__gte=start)
    agg = records.aggregate(
        total_revenue=Sum('revenue'),
        total_quantity=Sum('quantity'),
        total_orders=Count('id')
    )
    total_products = Product.objects.filter(is_active=True).count()
    active_alerts  = StockAlert.objects.filter(is_active=True).count()

    return {
        'total_revenue':   round(float(agg['total_revenue'] or 0), 2),
        'total_quantity':  int(agg['total_quantity'] or 0),
        'total_orders':    int(agg['total_orders'] or 0),
        'total_products':  total_products,
        'active_alerts':   active_alerts,
        'period_days':     days,
    }


# ─── Sales Trend ──────────────────────────────────────────────────────────────

def get_revenue_trend(days: int = 30) -> list:
    start = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(date__gte=start)
    trend = records.values('date').annotate(
        revenue=Sum('revenue'),
        quantity=Sum('quantity')
    ).order_by('date')
    return [
        {'date': r['date'].isoformat(), 'revenue': float(r['revenue'] or 0), 'quantity': int(r['quantity'] or 0)}
        for r in trend
    ]


def get_sales_trend(product_name: str = None, category_name: str = None, days: int = 30) -> list:
    start = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(date__gte=start)
    if product_name:
        records = records.filter(product__name__icontains=product_name)
    if category_name:
        records = records.filter(product__category__name__icontains=category_name)
    records = records.values('date').annotate(total=Sum('quantity')).order_by('date')
    return [{'date': r['date'].isoformat(), 'quantity': int(r['total'] or 0)} for r in records]


# ─── Top Products ─────────────────────────────────────────────────────────────

def get_top_products(days: int = 30, limit: int = 10) -> list:
    start = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(date__gte=start)
    top = records.values('product__name', 'product__sku', 'product__category__name').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('revenue')
    ).order_by('-total_quantity')[:limit]
    return [
        {
            'product': r['product__name'],
            'sku': r['product__sku'],
            'category': r['product__category__name'],
            'total_quantity': int(r['total_quantity'] or 0),
            'total_revenue': round(float(r['total_revenue'] or 0), 2),
        }
        for r in top
    ]


# ─── Category Distribution ────────────────────────────────────────────────────

def get_category_distribution(days: int = 30) -> list:
    start = timezone.now().date() - timedelta(days=days)
    records = SalesRecord.objects.filter(date__gte=start)
    dist = records.values('product__category__name').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('revenue')
    ).order_by('-total_quantity')
    return [
        {
            'category': r['product__category__name'] or 'Uncategorized',
            'total_quantity': int(r['total_quantity'] or 0),
            'total_revenue': round(float(r['total_revenue'] or 0), 2),
        }
        for r in dist
    ]


# ─── Forecast ─────────────────────────────────────────────────────────────────

def forecast_demand(product_name: str, horizon: int = 30) -> dict:
    """Main forecast function: tries Prophet first, falls back to RF."""
    try:
        product = Product.objects.get(name__icontains=product_name, is_active=True)
    except Product.DoesNotExist:
        # Try partial match
        products = Product.objects.filter(name__icontains=product_name, is_active=True)
        if not products.exists():
            return {'error': f'Product "{product_name}" not found.'}
        product = products.first()
    except Product.MultipleObjectsReturned:
        product = Product.objects.filter(name__icontains=product_name, is_active=True).first()

    # Try Prophet (Load only, do not train synchronously to avoid timeouts)
    from forecasting.engine.prophet_model import ProphetDemandModel
    pm = ProphetDemandModel(product.id)
    if pm.load():
        predictions = pm.predict(horizon)
        chart_config = pm.get_chart_config(horizon)
        if predictions:
            total_demand = sum(p['predicted_demand'] for p in predictions)
            return {
                'product': product.name,
                'sku': product.sku,
                'current_stock': product.stock,
                'horizon_days': horizon,
                'total_forecasted_demand': round(total_demand, 1),
                'reorder_point': product.reorder_point,
                'days_of_stock_remaining': round(product.stock / (total_demand / horizon), 1) if total_demand > 0 else 999,
                'forecast': predictions[:7],  # First 7 days inline
                'model': 'prophet',
                'chart_config': chart_config,
            }

    # Fallback to RandomForest
    from forecasting.engine.rf_model import rf_model
    if rf_model.is_trained or rf_model.load():
        predictions = rf_model.predict_future(product, horizon_days=horizon)
        if predictions:
            total_demand = sum(p['predicted_demand'] for p in predictions)
            return {
                'product': product.name,
                'sku': product.sku,
                'current_stock': product.stock,
                'horizon_days': horizon,
                'total_forecasted_demand': round(total_demand, 1),
                'forecast': predictions[:7],
                'model': 'random_forest',
                'chart_config': None,
            }

    return {'error': 'No trained model available. Run: python manage.py train_models'}


# ─── Stock Analysis ───────────────────────────────────────────────────────────

def get_items_running_out(days: int = 14) -> list:
    """Find products predicted to run out in the next N days using Prophet."""
    from forecasting.engine.prophet_model import get_or_train_prophet

    products = Product.objects.filter(is_active=True, stock__gte=0)
    running_out = []

    for product in products:
        if product.stock == 0:
            running_out.append({
                'product': product.name, 'sku': product.sku,
                'current_stock': 0, 'days_until_empty': 0,
                'severity': 'critical'
            })
            continue

        from forecasting.engine.prophet_model import ProphetDemandModel
        pm = ProphetDemandModel(product.id)
        if not pm.load():
            continue

        predictions = pm.predict(days)
        if not predictions:
            continue

        cum_demand = 0
        for i, pred in enumerate(predictions):
            cum_demand += pred['predicted_demand']
            if cum_demand >= product.stock:
                severity = 'critical' if (i + 1) <= 3 else ('warning' if (i + 1) <= 7 else 'info')
                running_out.append({
                    'product': product.name, 'sku': product.sku,
                    'current_stock': product.stock,
                    'days_until_empty': i + 1,
                    'total_forecasted_demand': round(cum_demand, 1),
                    'severity': severity
                })
                break

    running_out.sort(key=lambda x: x['days_until_empty'])
    return running_out[:20]


def get_reorder_recommendations() -> list:
    """Products that are below reorder point or will be shortly."""
    products = Product.objects.filter(is_active=True, stock__lte=F('reorder_point'))
    recs = []
    for p in products:
        recs.append({
            'product': p.name, 'sku': p.sku,
            'current_stock': p.stock,
            'reorder_point': p.reorder_point,
            'reorder_quantity': p.reorder_quantity,
            'supplier': p.supplier_name,
            'lead_time_days': p.lead_time_days,
            'urgency': 'critical' if p.stock == 0 else 'high'
        })
    return recs


# ─── Active Alerts ────────────────────────────────────────────────────────────

def get_active_alerts() -> list:
    alerts = StockAlert.objects.filter(is_active=True).select_related('product').order_by('-created_at')[:20]
    return [
        {
            'product': a.product.name, 'type': a.alert_type,
            'severity': a.severity, 'message': a.message,
            'days_until_stockout': a.days_until_stockout,
            'created_at': a.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for a in alerts
    ]
