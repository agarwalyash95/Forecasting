"""
LangGraph ReAct agent for the RetailIQ chatbot.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from forecasting.chatbot.tools import ALL_TOOLS
from forecasting.engine.query import forecast_demand

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are **RetailIQ**, an advanced AI-powered Retail Inventory & Demand Forecasting Assistant.

You help store managers and retail analysts with:
- 📊 **Demand Forecasting**: Predict future product demand using Prophet ML models
- 📈 **Sales Analytics**: Trends, top products, category performance, KPIs
- 🔔 **Stock Alerts**: Identify low-stock, out-of-stock, and overstock situations
- 🛒 **Reorder Recommendations**: Which products to restock and when
- 📦 **Live Inventory**: Real-time stock levels from the inventory system
- 🛠️ **Full Database Access**: Query or update the database directly using SQL when asked.

**Guidelines**:
- Be professional, concise, and data-driven in your responses
- Always use the available tools to fetch live data before answering
- Format numbers clearly (e.g., ₹1,23,456 for Indian rupees, or units with commas)
- Use **markdown** formatting: bold for numbers, bullet points for lists
- When forecasting, mention the model used (Prophet vs RandomForest) and any confidence notes
- If asked for a chart, tell the user that a visualization has been generated alongside your response
- Proactively highlight risks (e.g., stockouts within 7 days get special emphasis)
- If a product is not found, suggest similar names or ask for clarification
- **DATABASE ACCESS**: If the user asks to query or update data that requires raw SQL, FIRST use `tool_get_database_schema` to understand the tables. THEN use `tool_execute_sql` to run the query. Be careful with UPDATE and DELETE statements!
"""


@dataclass
class ChatResponse:
    text: str
    chart_config: Optional[dict] = field(default=None)
    session_id: Optional[int] = field(default=None)


def generate_response(user_message: str, session_id: int = None, is_admin: bool = False) -> ChatResponse:
    """
    Main entry point for the chatbot.
    Loads session history, invokes LangGraph ReAct agent, saves messages.
    """
    api_key   = getattr(settings, 'GEMINI_API_KEY', '')
    model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-3.1-pro-preview')

    if not api_key:
        return ChatResponse(text="⚠️ Error: API Key is not configured.")

    llm = ChatGoogleGenerativeAI(temperature=0.1, google_api_key=api_key, model=model_name)
    agent = create_react_agent(llm, tools=ALL_TOOLS)

    # ── Build message history ─────────────────────────────────────────────────
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    if session_id:
        _load_session_history(messages, session_id)

    messages.append(HumanMessage(content=user_message))

    # ── Invoke agent ─────────────────────────────────────────────────────────
    chart_config = None
    try:
        response = agent.invoke(
            {'messages': messages},
            config={"configurable": {"is_admin": is_admin}}
        )
        result_text = response['messages'][-1].content

        # Check if forecast was run — if so, generate chart config
        chart_config = _extract_chart_config(user_message)

        # ── Save to session ───────────────────────────────────────────────────
        if session_id:
            _save_messages(session_id, user_message, result_text, chart_config)

        return ChatResponse(text=result_text, chart_config=chart_config, session_id=session_id)

    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        return ChatResponse(
            text=f"⚠️ An error occurred: {str(e)}\n\nPlease try rephrasing your question.",
            session_id=session_id
        )


def _load_session_history(messages: list, session_id: int):
    """Append last 10 messages from the session to the message list."""
    try:
        from forecasting.models import ChatSession
        session = ChatSession.objects.get(id=session_id)
        recent = session.messages.order_by('-created_at')[:10]
        for msg in reversed(list(recent)):
            if msg.sender == 'user':
                messages.append(HumanMessage(content=msg.text))
            else:
                messages.append(AIMessage(content=msg.text))
    except Exception:
        pass


def _extract_chart_config(user_message: str) -> Optional[dict]:
    """
    If the message is a forecast request, generate a chart config.
    Looks for product names and returns Prophet chart if available.
    """
    forecast_keywords = ['forecast', 'predict', 'demand', 'next', 'future']
    if not any(kw in user_message.lower() for kw in forecast_keywords):
        return None

    # Extract horizon
    import re
    horizon = 30
    match = re.search(r'(\d+)\s*(day|week|month)', user_message.lower())
    if match:
        n = int(match.group(1))
        unit = match.group(2)
        horizon = n if unit == 'day' else (n * 7 if unit == 'week' else n * 30)

    # Try to find product name in message
    try:
        from forecasting.models import Product
        products = Product.objects.filter(is_active=True)
        for product in products:
            if product.name.lower() in user_message.lower():
                from forecasting.engine.prophet_model import ProphetDemandModel
                pm = ProphetDemandModel(product.id)
                if pm.load():
                    return pm.get_chart_config(min(horizon, 90))
    except Exception:
        pass
    return None


def _save_messages(session_id: int, user_text: str, bot_text: str, chart_config: dict = None):
    """Persist user and bot messages to the database."""
    try:
        from forecasting.models import ChatSession, ChatMessage
        session = ChatSession.objects.get(id=session_id)

        # Auto-title session from first user message
        if session.messages.count() == 0:
            session.title = user_text[:80]
            session.save(update_fields=['title'])

        ChatMessage.objects.create(session=session, sender='user', text=user_text)
        ChatMessage.objects.create(session=session, sender='bot', text=bot_text, chart_config=chart_config)
    except Exception as e:
        logger.warning("Failed to save chat messages: %s", e)


def get_or_create_session(user) -> int:
    """Get the current active session or create a new one."""
    from forecasting.models import ChatSession
    session = ChatSession.objects.filter(user=user).order_by('-updated_at').first()
    if not session:
        session = ChatSession.objects.create(user=user, title='New Session')
    return session.id


def create_new_session(user) -> int:
    """Create a brand-new chat session."""
    from forecasting.models import ChatSession
    session = ChatSession.objects.create(user=user, title='New Session')
    return session.id
