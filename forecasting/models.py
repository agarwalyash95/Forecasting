from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    reorder_point = models.IntegerField(default=10, help_text='Stock level that triggers a reorder alert')
    reorder_quantity = models.IntegerField(default=50, help_text='Recommended quantity to reorder')
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_email = models.EmailField(blank=True)
    lead_time_days = models.IntegerField(default=7, help_text='Days from order to delivery')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (SKU: {self.sku})"

    @property
    def profit_margin(self):
        if self.price > 0:
            return round(((self.price - self.cost_price) / self.price) * 100, 2)
        return 0


class SalesRecord(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales_records')
    date = models.DateField(db_index=True)
    quantity = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    channel = models.CharField(
        max_length=20,
        choices=[('online', 'Online'), ('in_store', 'In-Store'), ('wholesale', 'Wholesale')],
        default='online'
    )
    region = models.CharField(max_length=100, blank=True, default='')
    customer_name = models.CharField(max_length=200, blank=True, default='')
    customer_email = models.EmailField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['product', 'date', 'channel']
        indexes = [
            models.Index(fields=['date', 'product']),
            models.Index(fields=['product', 'date']),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.date}: {self.quantity} units"


class InventoryLog(models.Model):
    """Tracks real-time inventory level changes (simulated API updates)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_logs')
    stock_level = models.IntegerField()
    change_amount = models.IntegerField(help_text='Positive = stock in, Negative = stock out')
    change_type = models.CharField(
        max_length=20,
        choices=[
            ('sale', 'Sale'),
            ('return', 'Return'),
            ('restock', 'Restock'),
            ('adjustment', 'Adjustment'),
            ('api_sync', 'API Sync'),
        ],
        default='api_sync'
    )
    source = models.CharField(max_length=100, default='simulated_api')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        sign = '+' if self.change_amount >= 0 else ''
        return f"{self.product.name}: {sign}{self.change_amount} → {self.stock_level}"


class StockAlert(models.Model):
    SEVERITY_CHOICES = [
        ('critical', '🔴 Critical'),
        ('warning', '🟡 Warning'),
        ('info', '🔵 Info'),
    ]
    ALERT_TYPE_CHOICES = [
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('overstock', 'Overstock'),
        ('demand_spike', 'Demand Spike'),
        ('reorder_needed', 'Reorder Needed'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='warning')
    message = models.TextField()
    forecast_demand = models.FloatField(null=True, blank=True, help_text='Forecasted demand that triggered this alert')
    days_until_stockout = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity.upper()}] {self.product.name}: {self.alert_type}"


class ForecastCache(models.Model):
    """Caches Prophet forecast results to avoid recomputing on every query."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='forecast_cache')
    model_type = models.CharField(max_length=20, choices=[('prophet', 'Prophet'), ('rf', 'RandomForest')], default='prophet')
    horizon_days = models.IntegerField(default=30)
    forecast_data = models.JSONField(help_text='Serialized forecast: [{date, yhat, yhat_lower, yhat_upper}]')
    generated_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField()

    class Meta:
        ordering = ['-generated_at']
        unique_together = ['product', 'model_type', 'horizon_days']

    def __str__(self):
        return f"{self.product.name} [{self.model_type}] forecast — {self.generated_at.date()}"


class ChatSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions', null=True, blank=True)
    title = models.CharField(max_length=200, default='New Session')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Session #{self.id} — {self.title}"


class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=[('user', 'User'), ('bot', 'Bot')])
    text = models.TextField()
    chart_config = models.JSONField(null=True, blank=True, help_text='Chart.js config for inline chart rendering')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender}] {self.text[:60]}"
