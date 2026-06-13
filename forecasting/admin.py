from django.contrib import admin
from .models import Category, Product, SalesRecord, StockAlert, InventoryLog, ForecastCache, ChatSession, ChatMessage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'price', 'stock', 'reorder_point', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'sku', 'supplier_name']
    list_editable = ['stock', 'is_active']
    readonly_fields = ['created_at', 'updated_at', 'profit_margin']
    fieldsets = (
        ('Product Info', {'fields': ('name', 'sku', 'category', 'is_active')}),
        ('Pricing', {'fields': ('price', 'cost_price', 'profit_margin')}),
        ('Inventory', {'fields': ('stock', 'reorder_point', 'reorder_quantity')}),
        ('Supplier', {'fields': ('supplier_name', 'supplier_email', 'lead_time_days')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(SalesRecord)
class SalesRecordAdmin(admin.ModelAdmin):
    list_display = ['product', 'date', 'quantity', 'revenue', 'channel', 'region', 'customer_name']
    list_filter = ['channel', 'region', 'date']
    search_fields = ['product__name', 'customer_name', 'customer_email']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ['product', 'alert_type', 'severity', 'days_until_stockout', 'is_active', 'created_at']
    list_filter = ['severity', 'alert_type', 'is_active']
    search_fields = ['product__name']
    list_editable = ['is_active']
    actions = ['mark_resolved']

    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_active=False, resolved_at=timezone.now())
        self.message_user(request, f"{queryset.count()} alert(s) marked as resolved.")
    mark_resolved.short_description = "Mark selected alerts as resolved"


@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['product', 'stock_level', 'change_amount', 'change_type', 'source', 'timestamp']
    list_filter = ['change_type', 'source']
    search_fields = ['product__name']
    readonly_fields = ['timestamp']


@admin.register(ForecastCache)
class ForecastCacheAdmin(admin.ModelAdmin):
    list_display = ['product', 'model_type', 'horizon_days', 'generated_at', 'valid_until']
    list_filter = ['model_type']
    readonly_fields = ['generated_at']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'title', 'created_at', 'updated_at']
    search_fields = ['user__username', 'title']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'sender', 'text_preview', 'created_at']
    list_filter = ['sender']

    def text_preview(self, obj):
        return obj.text[:80]
    text_preview.short_description = 'Message'
