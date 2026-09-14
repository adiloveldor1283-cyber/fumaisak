import json
import time
import platform
import django
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q
from django.db import connection
from django.conf import settings
from django.core.paginator import Paginator

from main.models import SystemErrorLog, LockedPage, UserSession, CustomUser
from main.adminpanel import admin_required


def get_db_health():
    t0 = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        engine_name = connection.settings_dict.get('ENGINE', '').split('.')[-1]
        return {
            "connected": True,
            "latency_ms": latency_ms,
            "engine": engine_name,
            "error": None
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "connected": False,
            "latency_ms": latency_ms,
            "engine": "unknown",
            "error": str(e)
        }


def is_authorized_monitor(request):
    # 1. Admin/Staff session
    if request.user and request.user.is_authenticated:
        if getattr(request.user, 'role', '') == 'admin' or request.user.is_superuser or request.user.is_staff:
            return True, request.user

    # 2. API Key from header: X-Monitoring-Key or Authorization: Bearer <key>
    api_key = request.headers.get('X-Monitoring-Key') or request.META.get('HTTP_X_MONITORING_KEY')
    if not api_key:
        auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:].strip()

    valid_keys = []
    custom_key = getattr(settings, 'MONITORING_API_KEY', None)
    if custom_key:
        valid_keys.append(str(custom_key).strip())
    sec_key = getattr(settings, 'SECRET_KEY', '')
    if sec_key:
        valid_keys.append(sec_key[:32].strip())

    if api_key and api_key in valid_keys:
        return True, None

    return False, None


# ==============================================================================
# 📊 REST API: Tizim Salomatligi va Monitoring Xulosasi (Overview)
# ==============================================================================
@csrf_exempt
def api_monitoring_overview(request):
    is_auth, user = is_authorized_monitor(request)
    if not is_auth:
        return JsonResponse({"error": "Ruxsat berilmagan. Admin autentifikatsiyasi yoki X-Monitoring-Key talab qilinadi."}, status=401)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h_start = now - timedelta(hours=24)
    last_7d_start = now - timedelta(days=7)

    # DB Health
    db_health = get_db_health()

    # Errors stats
    unresolved_count = SystemErrorLog.objects.filter(is_resolved=False).count()
    resolved_count = SystemErrorLog.objects.filter(is_resolved=True).count()
    total_count = unresolved_count + resolved_count
    today_count = SystemErrorLog.objects.filter(timestamp__gte=today_start).count()
    last_24h_count = SystemErrorLog.objects.filter(timestamp__gte=last_24h_start).count()
    last_7d_count = SystemErrorLog.objects.filter(timestamp__gte=last_7d_start).count()

    # System Status Determination
    if not db_health["connected"] or unresolved_count >= 10:
        system_status = "critical"
    elif unresolved_count > 0 or db_health["latency_ms"] > 200:
        system_status = "warning"
    else:
        system_status = "healthy"

    # Top Exceptions
    top_exceptions = list(
        SystemErrorLog.objects.filter(is_resolved=False)
        .values('exception_type')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    # Top Failing URLs
    top_urls = list(
        SystemErrorLog.objects.filter(is_resolved=False)
        .values('url_path')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    # Breakdown by role
    role_breakdown = list(
        SystemErrorLog.objects.values('user_role')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # Active counts
    active_sessions_count = UserSession.objects.filter(is_active=True).count()
    locked_pages_count = LockedPage.objects.count()

    # Recent 5 unresolved errors
    recent_qs = SystemErrorLog.objects.filter(is_resolved=False).select_related('user').order_by('-timestamp')[:5]
    recent_errors = []
    for err in recent_qs:
        user_name = err.user.get_full_name() if err.user else "Anonim"
        recent_errors.append({
            "id": err.id,
            "exception_type": err.exception_type or "UnhandledException",
            "error_message": err.error_message[:150],
            "url_path": err.url_path,
            "http_method": err.http_method,
            "user_role": err.user_role or "anonymous",
            "user_phone": err.user_phone or "",
            "user_name": user_name,
            "ip_address": err.ip_address or "",
            "timestamp": err.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })

    data = {
        "status": system_status,
        "timestamp": now.isoformat(),
        "database": db_health,
        "metrics": {
            "unresolved_errors": unresolved_count,
            "resolved_errors": resolved_count,
            "total_errors": total_count,
            "today_errors": today_count,
            "last_24h_errors": last_24h_count,
            "last_7d_errors": last_7d_count,
            "active_sessions": active_sessions_count,
            "locked_pages": locked_pages_count
        },
        "top_exceptions": top_exceptions,
        "top_urls": top_urls,
        "role_breakdown": role_breakdown,
        "recent_errors": recent_errors,
        "server": {
            "python_version": platform.python_version(),
            "django_version": django.get_version(),
            "debug_mode": settings.DEBUG,
            "server_time": now.strftime("%Y-%m-%d %H:%M:%S UTC%z")
        }
    }
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})


# ==============================================================================
# 📋 REST API: Xatoliklar ro'yxati (Filtr va Paginatsiya bilan)
# ==============================================================================
@csrf_exempt
def api_monitoring_errors(request):
    is_auth, user = is_authorized_monitor(request)
    if not is_auth:
        return JsonResponse({"error": "Ruxsat berilmagan."}, status=401)

    status_filter = request.GET.get('status', 'unresolved').lower()
    role_filter = request.GET.get('role', '').strip()
    method_filter = request.GET.get('method', '').strip().upper()
    search = request.GET.get('search', '').strip()
    page_number = int(request.GET.get('page', 1) or 1)
    page_size = min(int(request.GET.get('page_size', 20) or 20), 100)

    qs = SystemErrorLog.objects.select_related('user', 'resolved_by').order_by('-timestamp')

    if status_filter == 'unresolved':
        qs = qs.filter(is_resolved=False)
    elif status_filter == 'resolved':
        qs = qs.filter(is_resolved=True)

    if role_filter:
        qs = qs.filter(user_role__iexact=role_filter)

    if method_filter:
        qs = qs.filter(http_method=method_filter)

    if search:
        qs = qs.filter(
            Q(url_path__icontains=search) |
            Q(error_message__icontains=search) |
            Q(traceback__icontains=search) |
            Q(exception_type__icontains=search) |
            Q(user_phone__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__username__icontains=search)
        )

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_number)

    results = []
    for log in page_obj.object_list:
        user_info = None
        if log.user:
            user_info = {
                "id": log.user.id,
                "username": log.user.username,
                "full_name": log.user.get_full_name() or log.user.username,
                "phone": log.user.phone_number or log.user_phone or "",
                "role": log.user.role
            }

        resolved_by_info = None
        if log.resolved_by:
            resolved_by_info = {
                "id": log.resolved_by.id,
                "username": log.resolved_by.username,
                "full_name": log.resolved_by.get_full_name() or log.resolved_by.username
            }

        # Parse request_data JSON if possible
        parsed_request_data = None
        if log.request_data:
            try:
                parsed_request_data = json.loads(log.request_data)
            except Exception:
                parsed_request_data = log.request_data

        results.append({
            "id": log.id,
            "url_path": log.url_path,
            "http_method": log.http_method,
            "exception_type": log.exception_type or "UnhandledException",
            "error_message": log.error_message,
            "traceback": log.traceback,
            "ip_address": log.ip_address or "",
            "user_agent": log.user_agent or "",
            "request_data": parsed_request_data,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp_iso": log.timestamp.isoformat(),
            "user_role": log.user_role or "anonymous",
            "user_phone": log.user_phone or "",
            "user": user_info,
            "is_resolved": log.is_resolved,
            "resolved_at": log.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if log.resolved_at else None,
            "resolved_by": resolved_by_info
        })

    return JsonResponse({
        "success": True,
        "count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "results": results
    }, json_dumps_params={'ensure_ascii': False})


# ==============================================================================
# ✅ REST API: Xatolikni hal etildi deb belgilash (Resolve)
# ==============================================================================
@csrf_exempt
@require_http_methods(["POST"])
def api_monitoring_resolve_error(request, error_id):
    is_auth, user = is_authorized_monitor(request)
    if not is_auth:
        return JsonResponse({"error": "Ruxsat berilmagan."}, status=401)

    log = get_object_or_404(SystemErrorLog, id=error_id)
    log.is_resolved = True
    log.resolved_at = timezone.now()
    if user:
        log.resolved_by = user
    log.save()

    return JsonResponse({
        "success": True,
        "message": f"Xatolik #{error_id} muvaffaqiyatli hal etildi deb belgilandi.",
        "id": error_id,
        "resolved_at": log.resolved_at.strftime("%Y-%m-%d %H:%M:%S")
    })


# ==============================================================================
# 🧹 REST API: Barcha / Tanlangan xatoliklarni ommaviy hal etish (Bulk Resolve)
# ==============================================================================
@csrf_exempt
@require_http_methods(["POST"])
def api_monitoring_bulk_resolve(request):
    is_auth, user = is_authorized_monitor(request)
    if not is_auth:
        return JsonResponse({"error": "Ruxsat berilmagan."}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    ids = body.get('ids', [])
    resolve_all = body.get('all_unresolved', False)

    now = timezone.now()
    resolved_by_user = user if user else None

    if resolve_all:
        count = SystemErrorLog.objects.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_at=now,
            resolved_by=resolved_by_user
        )
    elif ids and isinstance(ids, list):
        count = SystemErrorLog.objects.filter(id__in=ids, is_resolved=False).update(
            is_resolved=True,
            resolved_at=now,
            resolved_by=resolved_by_user
        )
    else:
        return JsonResponse({"error": "Hech qanday ID yoki all_unresolved parametri berilmadi."}, status=400)

    return JsonResponse({
        "success": True,
        "message": f"{count} ta xatolik muvaffaqiyatli hal etildi deb belgilandi.",
        "resolved_count": count
    })


# ==============================================================================
# 🖥️ ADMIN DASHBOARD VIEW (HTML Render)
# ==============================================================================
@admin_required
def admin_monitoring_dashboard(request):
    current_status = request.GET.get('status', 'unresolved')
    query = request.GET.get('query', '')
    role = request.GET.get('role', '')
    method = request.GET.get('method', '')

    logs_qs = SystemErrorLog.objects.select_related('user', 'resolved_by').order_by('-timestamp')

    if current_status == 'resolved':
        logs_qs = logs_qs.filter(is_resolved=True)
    elif current_status == 'unresolved':
        logs_qs = logs_qs.filter(is_resolved=False)

    if role:
        logs_qs = logs_qs.filter(user_role__iexact=role)

    if method:
        logs_qs = logs_qs.filter(http_method=method)

    if query:
        logs_qs = logs_qs.filter(
            Q(url_path__icontains=query) |
            Q(error_message__icontains=query) |
            Q(traceback__icontains=query) |
            Q(exception_type__icontains=query) |
            Q(user_phone__icontains=query) |
            Q(ip_address__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )

    # Pagination
    paginator = Paginator(logs_qs, 25)
    page_number = request.GET.get('page', 1)
    logs_page = paginator.get_page(page_number)

    # Overview stats for cards
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h_start = now - timedelta(hours=24)

    unresolved_count = SystemErrorLog.objects.filter(is_resolved=False).count()
    resolved_count = SystemErrorLog.objects.filter(is_resolved=True).count()
    today_count = SystemErrorLog.objects.filter(timestamp__gte=today_start).count()
    last_24h_count = SystemErrorLog.objects.filter(timestamp__gte=last_24h_start).count()
    locked_count = LockedPage.objects.count()

    db_health = get_db_health()

    context = {
        'logs': logs_page,
        'unresolved_count': unresolved_count,
        'resolved_count': resolved_count,
        'today_count': today_count,
        'last_24h_count': last_24h_count,
        'locked_count': locked_count,
        'db_health': db_health,
        'current_status': current_status,
        'query': query,
        'role': role,
        'method': method,
        'server_info': {
            'python_version': platform.python_version(),
            'django_version': django.get_version(),
            'debug_mode': settings.DEBUG,
            'server_time': now.strftime("%d.%m.%Y %H:%M:%S")
        }
    }
    return render(request, 'admin_monitoring_dashboard.html', context)
