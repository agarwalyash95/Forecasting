"""
DRF API Views for all endpoints.
"""
import json
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from forecasting.models import Product, Category, SalesRecord, StockAlert, InventoryLog
from forecasting.api.serializers import (
    ProductSerializer, CategorySerializer, SalesRecordSerializer,
    StockAlertSerializer, InventoryLogSerializer,
    KPISerializer, ChatRequestSerializer, ChatResponseSerializer
)
from forecasting.engine.query import (
    get_summary_kpis, get_revenue_trend, get_sales_trend,
    get_top_products, get_category_distribution, forecast_demand,
    get_items_running_out, get_reorder_recommendations, get_active_alerts
)
from forecasting.inventory_api.simulator import get_inventory_snapshot, simulate_inventory_sync

logger = logging.getLogger(__name__)


# ─── Auth token endpoint ───────────────────────────────────────────────────────

from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token


class LoginView(ObtainAuthToken):
    """POST /api/auth/login/ — returns token"""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user_id': user.id, 'username': user.username})


# ─── Chatbot ──────────────────────────────────────────────────────────────────

class ChatbotView(APIView):
    """POST /api/chat/ — main chatbot endpoint"""
    permission_classes = [AllowAny]  # Allow unauthenticated for demo

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_message = serializer.validated_data['message']
        session_id   = serializer.validated_data.get('session_id')

        # Create session if not provided
        if not session_id and request.user.is_authenticated:
            from forecasting.chatbot.agent import get_or_create_session
            session_id = get_or_create_session(request.user)

        from forecasting.chatbot.agent import generate_response
        chat_response = generate_response(user_message, session_id=session_id)

        return Response({
            'text':         chat_response.text,
            'chart_config': chat_response.chart_config,
            'session_id':   chat_response.session_id,
        })


class NewSessionView(APIView):
    """POST /api/chat/new-session/ — create a new chat session"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from forecasting.chatbot.agent import create_new_session
        session_id = create_new_session(request.user)
        return Response({'session_id': session_id})


# ─── KPIs & Analytics ─────────────────────────────────────────────────────────

class KPIView(APIView):
    """GET /api/kpis/?days=30"""
    permission_classes = [AllowAny]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        data = get_summary_kpis(days)
        return Response(data)


class RevenueTrendView(APIView):
    """GET /api/trend/revenue/?days=30"""
    permission_classes = [AllowAny]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        data = get_revenue_trend(days)
        return Response(data)


class SalesTrendView(APIView):
    """GET /api/trend/sales/?days=30&product=&category="""
    permission_classes = [AllowAny]

    def get(self, request):
        days     = int(request.query_params.get('days', 30))
        product  = request.query_params.get('product', '')
        category = request.query_params.get('category', '')
        data = get_sales_trend(product or None, category or None, days)
        return Response(data)


class TopProductsView(APIView):
    """GET /api/products/top/?days=30&limit=10"""
    permission_classes = [AllowAny]

    def get(self, request):
        days  = int(request.query_params.get('days', 30))
        limit = int(request.query_params.get('limit', 10))
        data  = get_top_products(days, limit)
        return Response(data)


class CategoryAnalysisView(APIView):
    """GET /api/categories/analysis/?days=30"""
    permission_classes = [AllowAny]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        data = get_category_distribution(days)
        return Response(data)


# ─── Forecasting ──────────────────────────────────────────────────────────────

class ForecastView(APIView):
    """GET /api/forecast/?product=Laptop&horizon=30"""
    permission_classes = [AllowAny]

    def get(self, request):
        product_name = request.query_params.get('product', '')
        horizon      = int(request.query_params.get('horizon', 30))

        if not product_name:
            return Response({'error': 'product parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        data = forecast_demand(product_name, horizon)
        return Response(data)


class ItemsRunningOutView(APIView):
    """GET /api/forecast/running-out/?days=14"""
    permission_classes = [AllowAny]

    def get(self, request):
        days = int(request.query_params.get('days', 14))
        data = get_items_running_out(days)
        return Response(data)


class ReorderRecommendationsView(APIView):
    """GET /api/forecast/reorder/"""
    permission_classes = [AllowAny]

    def get(self, request):
        data = get_reorder_recommendations()
        return Response(data)


# ─── Inventory ────────────────────────────────────────────────────────────────

class InventorySnapshotView(APIView):
    """GET /api/inventory/ — current stock levels"""
    permission_classes = [AllowAny]

    def get(self, request):
        data = get_inventory_snapshot()
        return Response(data)


class InventorySyncView(APIView):
    """POST /api/inventory/sync/ — trigger simulated API sync"""
    permission_classes = [AllowAny]

    def post(self, request):
        data = simulate_inventory_sync()
        return Response({'synced': len(data), 'snapshot': data[:10]})


# ─── Alerts ───────────────────────────────────────────────────────────────────

class StockAlertsView(APIView):
    """GET /api/alerts/"""
    permission_classes = [AllowAny]

    def get(self, request):
        data = get_active_alerts()
        return Response(data)


class ResolveAlertView(APIView):
    """POST /api/alerts/<id>/resolve/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from django.utils import timezone
        try:
            alert = StockAlert.objects.get(pk=pk)
            alert.is_active = False
            alert.resolved_at = timezone.now()
            alert.save(update_fields=['is_active', 'resolved_at'])
            return Response({'status': 'resolved'})
        except StockAlert.DoesNotExist:
            return Response({'error': 'Alert not found'}, status=status.HTTP_404_NOT_FOUND)


# ─── Products CRUD ────────────────────────────────────────────────────────────

class ProductListView(generics.ListAPIView):
    """GET /api/products/"""
    queryset = Product.objects.filter(is_active=True).select_related('category').order_by('name')
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        search   = self.request.query_params.get('search')
        if category:
            qs = qs.filter(category__name__icontains=category)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class CategoryListView(generics.ListAPIView):
    """GET /api/categories/"""
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
