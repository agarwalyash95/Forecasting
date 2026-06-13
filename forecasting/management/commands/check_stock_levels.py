"""
Management command: check_stock_levels
Scans all products, runs Prophet forecasts, creates StockAlert records for at-risk products.
Usage: python manage.py check_stock_levels
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from forecasting.models import Product, StockAlert
from forecasting.engine.query import get_items_running_out, get_reorder_recommendations


class Command(BaseCommand):
    help = 'Scan stock levels and create alerts for at-risk products'

    def handle(self, *args, **options):
        self.stdout.write('🔔 Checking stock levels...')
        alerts_created = 0

        # Out-of-stock alerts
        out_of_stock = Product.objects.filter(is_active=True, stock=0)
        for product in out_of_stock:
            StockAlert.objects.update_or_create(
                product=product,
                alert_type='out_of_stock',
                is_active=True,
                defaults={
                    'severity': 'critical',
                    'message': f'{product.name} is OUT OF STOCK. Immediate restock required.',
                    'days_until_stockout': 0,
                }
            )
            alerts_created += 1

        # Demand-forecast-based running out alerts
        running_out = get_items_running_out(days=14)
        for item in running_out:
            try:
                product = Product.objects.get(name=item['product'])
                severity = item.get('severity', 'warning')
                days = item.get('days_until_empty', 0)
                StockAlert.objects.update_or_create(
                    product=product,
                    alert_type='low_stock',
                    is_active=True,
                    defaults={
                        'severity': severity,
                        'message': (
                            f'{product.name} is forecast to run out in {days} day(s). '
                            f'Current stock: {product.stock} units. '
                            f'Forecasted demand: {item.get("total_forecasted_demand", "N/A")} units.'
                        ),
                        'forecast_demand': item.get('total_forecasted_demand'),
                        'days_until_stockout': days,
                    }
                )
                alerts_created += 1
            except Product.DoesNotExist:
                continue

        # Reorder point alerts
        reorder = get_reorder_recommendations()
        for item in reorder:
            try:
                product = Product.objects.get(sku=item['sku'])
                StockAlert.objects.update_or_create(
                    product=product,
                    alert_type='reorder_needed',
                    is_active=True,
                    defaults={
                        'severity': item['urgency'] == 'critical' and 'critical' or 'warning',
                        'message': (
                            f'{product.name} needs reorder. Stock ({product.stock}) is at/below reorder point '
                            f'({product.reorder_point}). Order {product.reorder_quantity} from {product.supplier_name}.'
                        ),
                    }
                )
                alerts_created += 1
            except Product.DoesNotExist:
                continue

        self.stdout.write(self.style.SUCCESS(f'✅ {alerts_created} stock alert(s) created/updated.'))
