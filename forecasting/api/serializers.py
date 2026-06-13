"""
DRF Serializers for all API response models.
"""
from rest_framework import serializers
from forecasting.models import (
    Product, Category, SalesRecord, StockAlert,
    InventoryLog, ChatSession, ChatMessage, ForecastCache
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    profit_margin = serializers.FloatField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category', 'category_name',
            'price', 'cost_price', 'profit_margin',
            'stock', 'reorder_point', 'reorder_quantity',
            'supplier_name', 'supplier_email', 'lead_time_days',
            'is_active'
        ]


class SalesRecordSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = SalesRecord
        fields = ['id', 'product', 'product_name', 'date', 'quantity', 'revenue', 'channel', 'region', 'customer_name']


class StockAlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku  = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = StockAlert
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'alert_type', 'severity', 'message',
            'forecast_demand', 'days_until_stockout',
            'is_active', 'created_at'
        ]


class InventoryLogSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = InventoryLog
        fields = ['id', 'product', 'product_name', 'stock_level', 'change_amount', 'change_type', 'source', 'timestamp']


# ── Chatbot ────────────────────────────────────────────────────────────────────

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'sender', 'text', 'chart_config', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'created_at', 'updated_at', 'messages']


# ── Analytics (non-model) ─────────────────────────────────────────────────────

class KPISerializer(serializers.Serializer):
    total_revenue   = serializers.FloatField()
    total_quantity  = serializers.IntegerField()
    total_orders    = serializers.IntegerField()
    total_products  = serializers.IntegerField()
    active_alerts   = serializers.IntegerField()
    period_days     = serializers.IntegerField()


class TrendPointSerializer(serializers.Serializer):
    date     = serializers.DateField()
    revenue  = serializers.FloatField(required=False)
    quantity = serializers.IntegerField(required=False)


class ForecastPointSerializer(serializers.Serializer):
    date             = serializers.CharField()
    predicted_demand = serializers.FloatField()
    lower_bound      = serializers.FloatField(required=False, allow_null=True)
    upper_bound      = serializers.FloatField(required=False, allow_null=True)
    model            = serializers.CharField(required=False)


class ChatRequestSerializer(serializers.Serializer):
    message    = serializers.CharField(max_length=2000)
    session_id = serializers.IntegerField(required=False, allow_null=True)


class ChatResponseSerializer(serializers.Serializer):
    text         = serializers.CharField()
    chart_config = serializers.DictField(required=False, allow_null=True)
    session_id   = serializers.IntegerField(required=False, allow_null=True)
