"""
LangGraph tool definitions for the RetailIQ chatbot agent.
Each tool queries the forecasting engine and returns structured data.
"""
import json
import logging
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from forecasting.engine import (
    forecast_demand, get_summary_kpis, get_sales_trend,
    get_revenue_trend, get_top_products, get_category_distribution,
    get_items_running_out, get_reorder_recommendations, get_active_alerts
)
from forecasting.inventory_api.simulator import get_inventory_snapshot, simulate_inventory_sync

logger = logging.getLogger(__name__)


@tool
def tool_forecast_demand(product_name: str, horizon_days: int = 30) -> str:
    """
    Forecast demand for a specific product for the next N days.
    Uses Prophet time-series model (falls back to RandomForest).
    Returns predicted units, confidence intervals, and stock-out risk.
    Example: tool_forecast_demand("Laptop", 30)
    """
    result = forecast_demand(product_name, horizon_days)
    # Remove chart_config from tool text (too large for LLM context)
    result_clean = {k: v for k, v in result.items() if k != 'chart_config'}
    return json.dumps(result_clean, default=str)


@tool
def tool_get_kpis(days: int = 30) -> str:
    """
    Get overall store KPIs for the last N days:
    total revenue, total quantity sold, order count, active stock alerts.
    """
    return json.dumps(get_summary_kpis(days), default=str)


@tool
def tool_get_sales_trend(days: int = 30, product_name: str = '', category_name: str = '') -> str:
    """
    Get daily sales quantity trend over the last N days.
    Optionally filter by product name or category name.
    """
    data = get_sales_trend(product_name or None, category_name or None, days)
    return json.dumps(data, default=str)


@tool
def tool_get_top_products(days: int = 30, limit: int = 10) -> str:
    """
    Get the top-selling products by quantity over the last N days.
    Returns product name, SKU, category, total units sold, and total revenue.
    """
    return json.dumps(get_top_products(days, limit), default=str)


@tool
def tool_get_category_analysis(days: int = 30) -> str:
    """
    Get sales distribution by product category over the last N days.
    Useful for understanding which categories drive the most revenue.
    """
    return json.dumps(get_category_distribution(days), default=str)


@tool
def tool_get_stock_alerts() -> str:
    """
    Get all active inventory stock alerts (low stock, out of stock, demand spikes).
    Returns severity, alert type, and days until stockout.
    """
    alerts = get_active_alerts()
    if not alerts:
        return "No active stock alerts. All inventory levels are healthy."
    return json.dumps(alerts, default=str)


@tool
def tool_get_items_running_out(days: int = 14) -> str:
    """
    Find products predicted to run out of stock within the next N days.
    Uses ML demand forecasting to estimate days until stockout.
    """
    items = get_items_running_out(days)
    if not items:
        return f"No products are predicted to run out of stock in the next {days} days."
    return json.dumps(items, default=str)


@tool
def tool_get_inventory_snapshot() -> str:
    """
    Get a real-time inventory snapshot from the integrated inventory system.
    Returns current stock levels, reorder points, and stock health status for all products.
    """
    snapshot = get_inventory_snapshot()
    if not snapshot:
        return "No inventory data available."
    return json.dumps(snapshot[:30], default=str)  # Limit to 30 for context size


@tool
def tool_get_reorder_recommendations() -> str:
    """
    Get a list of products that need to be reordered immediately.
    Products currently at or below their reorder point with supplier details.
    """
    recs = get_reorder_recommendations()
    if not recs:
        return "All products are currently above their reorder points. No immediate restocking needed."
    return json.dumps(recs, default=str)


@tool
def tool_update_item_quantity(product_name: str, quantity: int, config: RunnableConfig) -> str:
    """
    Update the inventory stock level for a specific product manually.
    Only use this if the user explicitly asks to update or set the quantity/stock.
    """
    is_admin = config.get("configurable", {}).get("is_admin", False)
    if not is_admin:
        return "Permission Denied: Only administrators can update inventory quantities."
        
    from forecasting.models import Product, InventoryLog
    product = Product.objects.filter(name__icontains=product_name, is_active=True).first()
    if not product:
        return f"Product '{product_name}' not found."
        
    old_stock = product.stock
    product.stock = quantity
    product.save(update_fields=['stock'])
    
    InventoryLog.objects.create(
        product=product,
        stock_level=quantity,
        change_amount=quantity - old_stock,
        change_type='adjustment',
        source='chatbot_manual'
    )
    return f"Successfully updated '{product.name}' stock from {old_stock} to {quantity}."

@tool
def tool_get_database_schema() -> str:
    """
    Get the complete database schema including all tables and columns.
    Use this to understand the database structure before writing raw SQL queries.
    """
    from django.db import connection
    
    schema_info = []
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        for table in tables:
            # Note: We omit system tables to save context space if desired, but we can return all.
            if table.startswith('django_') or table.startswith('auth_'):
                continue
                
            try:
                relations = connection.introspection.get_relations(cursor, table)
                desc = connection.introspection.get_table_description(cursor, table)
                
                columns = []
                for col in desc:
                    col_name = col.name
                    col_type = col.type_code
                    columns.append(f"{col_name} ({col_type})")
                    
                schema_info.append(f"Table: {table}\\nColumns: {', '.join(columns)}")
            except Exception as e:
                logger.warning(f"Failed to get schema for {table}: {e}")
                
    return "\\n\\n".join(schema_info)


@tool
def tool_execute_sql(query: str, config: RunnableConfig) -> str:
    """
    Execute a raw SQL query against the database.
    WARNING: Only use this for complex queries that the other tools cannot handle,
    or if the user explicitly asks to fetch or update specific data directly.
    """
    is_admin = config.get("configurable", {}).get("is_admin", False)
    if not is_admin:
        return "Permission Denied: Only administrators can execute raw SQL queries."
        
    from django.db import connection
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            
            # If it's a SELECT query, fetch and return results
            if query.strip().upper().startswith('SELECT'):
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                # Limit to 50 rows to prevent context overflow
                if len(rows) > 50:
                    rows = rows[:50]
                    warning = "\\n(Note: Results truncated to 50 rows)"
                else:
                    warning = ""
                    
                result = [dict(zip(columns, row)) for row in rows]
                return json.dumps(result, default=str) + warning
            else:
                # For UPDATE, INSERT, DELETE
                connection.commit()
                return f"Query executed successfully. Rows affected: {cursor.rowcount}"
    except Exception as e:
        return f"SQL Execution Error: {str(e)}"


ALL_TOOLS = [
    tool_forecast_demand,
    tool_get_kpis,
    tool_get_sales_trend,
    tool_get_top_products,
    tool_get_category_analysis,
    tool_get_stock_alerts,
    tool_get_items_running_out,
    tool_get_inventory_snapshot,
    tool_get_reorder_recommendations,
    tool_update_item_quantity,
    tool_get_database_schema,
    tool_execute_sql,
]
