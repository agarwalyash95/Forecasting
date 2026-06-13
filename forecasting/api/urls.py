from django.urls import path
from forecasting.api import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('auth/login/', views.LoginView.as_view(), name='api-login'),

    # ── Chatbot ───────────────────────────────────────────────────────────────
    path('chat/', views.ChatbotView.as_view(), name='api-chat'),
    path('chat/new-session/', views.NewSessionView.as_view(), name='api-new-session'),

    # ── KPIs & Trends ─────────────────────────────────────────────────────────
    path('kpis/', views.KPIView.as_view(), name='api-kpis'),
    path('trend/revenue/', views.RevenueTrendView.as_view(), name='api-revenue-trend'),
    path('trend/sales/', views.SalesTrendView.as_view(), name='api-sales-trend'),

    # ── Products & Categories ─────────────────────────────────────────────────
    path('products/', views.ProductListView.as_view(), name='api-products'),
    path('products/top/', views.TopProductsView.as_view(), name='api-top-products'),
    path('categories/', views.CategoryListView.as_view(), name='api-categories'),
    path('categories/analysis/', views.CategoryAnalysisView.as_view(), name='api-category-analysis'),

    # ── Forecasting ───────────────────────────────────────────────────────────
    path('forecast/', views.ForecastView.as_view(), name='api-forecast'),
    path('forecast/running-out/', views.ItemsRunningOutView.as_view(), name='api-running-out'),
    path('forecast/reorder/', views.ReorderRecommendationsView.as_view(), name='api-reorder'),

    # ── Inventory ─────────────────────────────────────────────────────────────
    path('inventory/', views.InventorySnapshotView.as_view(), name='api-inventory'),
    path('inventory/sync/', views.InventorySyncView.as_view(), name='api-inventory-sync'),

    # ── Alerts ────────────────────────────────────────────────────────────────
    path('alerts/', views.StockAlertsView.as_view(), name='api-alerts'),
    path('alerts/<int:pk>/resolve/', views.ResolveAlertView.as_view(), name='api-resolve-alert'),
]
