"""
Browser-facing Django views (non-API).
"""
import json
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from rest_framework.authtoken.models import Token

from forecasting.models import ChatSession
from forecasting.engine.query import get_summary_kpis, get_active_alerts


def index(request):
    """Home page — redirects to dashboard if logged in, else login page."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login_page')


def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Check if user exists and is inactive before authenticating
        try:
            u = User.objects.get(username=username)
            if not u.is_active:
                return render(request, 'forecasting/login.html', {'error': 'Your account is pending admin approval.'})
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            token, _ = Token.objects.get_or_create(user=user)
            request.session['auth_token'] = token.key
            return redirect('dashboard')
        return render(request, 'forecasting/login.html', {'error': 'Invalid credentials'})
    return render(request, 'forecasting/login.html')

def register_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email', '')
        
        if User.objects.filter(username=username).exists():
            return render(request, 'forecasting/register.html', {'error': 'Username already exists.'})
            
        # Create user but set to inactive until admin approves
        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False
        user.save()
        
        return render(request, 'forecasting/login.html', {
            'message': 'Registration successful! Your account is pending admin approval.'
        })
    return render(request, 'forecasting/register.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login_page')


@login_required
def dashboard(request):
    kpis   = get_summary_kpis(30)
    alerts = get_active_alerts()[:5]
    token  = request.session.get('auth_token', '')
    
    pending_users = []
    if request.user.is_superuser:
        pending_users = User.objects.filter(is_active=False).order_by('-date_joined')
        
    return render(request, 'forecasting/dashboard.html', {
        'kpis': kpis,
        'alerts': alerts,
        'auth_token': token,
        'pending_users': pending_users,
    })

@login_required
def approve_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        user_to_approve = User.objects.get(id=user_id, is_active=False)
        user_to_approve.is_active = True
        user_to_approve.save()
        return redirect('dashboard')
    except User.DoesNotExist:
        return redirect('dashboard')

@login_required
def reject_user(request, user_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        user_to_reject = User.objects.get(id=user_id, is_active=False)
        user_to_reject.delete()
        return redirect('dashboard')
    except User.DoesNotExist:
        return redirect('dashboard')


@login_required
def chatbot_view(request):
    sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')[:10]
    current_session_id = request.GET.get('session_id')
    messages = []
    if current_session_id:
        try:
            session = ChatSession.objects.get(id=current_session_id, user=request.user)
            messages = list(session.messages.order_by('created_at').values('sender', 'text', 'chart_config', 'created_at'))
        except ChatSession.DoesNotExist:
            pass
    token = request.session.get('auth_token', '')
    return render(request, 'forecasting/chatbot.html', {
        'sessions': sessions,
        'current_session_id': current_session_id,
        'messages_json': json.dumps(messages, default=str),
        'auth_token': token,
    })
