"""
Simulated real-time inventory API.
Returns realistic stock fluctuations to mimic a live WMS/ERP integration.
"""
import random
import json
import logging
from datetime import datetime
from django.utils import timezone
from forecasting.models import Product, InventoryLog

logger = logging.getLogger(__name__)


def simulate_inventory_sync() -> list:
    """
    Simulate a real-time inventory API sync.
    Applies small random stock changes (sales, returns, restocks) and logs them.
    Returns current inventory snapshot.
    """
    products = Product.objects.filter(is_active=True).select_related('category')
    snapshot = []

    for product in products:
        # Simulate random stock event
        event_type = random.choices(
            ['sale', 'return', 'restock', 'no_change'],
            weights=[0.50, 0.10, 0.15, 0.25]
        )[0]

        change = 0
        if event_type == 'sale':
            change = -random.randint(1, max(1, min(5, product.stock)))
        elif event_type == 'return':
            change = random.randint(1, 3)
        elif event_type == 'restock' and product.stock < product.reorder_point * 2:
            change = product.reorder_quantity

        if change != 0:
            new_stock = max(0, product.stock + change)
            product.stock = new_stock
            product.save(update_fields=['stock'])

            InventoryLog.objects.create(
                product=product,
                stock_level=new_stock,
                change_amount=change,
                change_type=event_type,
                source='simulated_api'
            )

        snapshot.append({
            'product_id': product.id,
            'product': product.name,
            'sku': product.sku,
            'category': product.category.name if product.category else 'N/A',
            'current_stock': product.stock,
            'reorder_point': product.reorder_point,
            'status': _stock_status(product),
            'last_event': event_type,
            'change': change,
            'synced_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        })

    logger.info("Inventory sync completed: %d products updated", len(snapshot))
    return snapshot


def get_inventory_snapshot() -> list:
    """Read current stock levels without applying changes."""
    products = Product.objects.filter(is_active=True).select_related('category').order_by('name')
    return [
        {
            'product_id': p.id,
            'product': p.name,
            'sku': p.sku,
            'category': p.category.name if p.category else 'N/A',
            'current_stock': p.stock,
            'reorder_point': p.reorder_point,
            'reorder_quantity': p.reorder_quantity,
            'lead_time_days': p.lead_time_days,
            'status': _stock_status(p),
            'price': float(p.price),
            'supplier': p.supplier_name,
        }
        for p in products
    ]


def _stock_status(product) -> str:
    if product.stock == 0:
        return 'out_of_stock'
    elif product.stock <= product.reorder_point:
        return 'low_stock'
    elif product.stock > product.reorder_point * 5:
        return 'overstock'
    return 'healthy'
