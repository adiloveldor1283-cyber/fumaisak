import json
import urllib.request
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.contrib.sessions.models import Session
from django.core.cache import cache
from main.models import UserSession


def parse_user_agent(ua_string):
    if not ua_string:
        return 'Unknown', 'Unknown', 'Unknown'

    ua = ua_string.lower()

    if 'mobi' in ua or 'iphone' in ua or 'android' in ua:
        device_type = 'Mobile'
    elif 'ipad' in ua or 'tablet' in ua:
        device_type = 'Tablet'
    else:
        device_type = 'PC'

    if 'chrome' in ua and 'safari' in ua and 'edge' not in ua and 'edg' not in ua:
        browser = 'Chrome'
    elif 'safari' in ua and 'chrome' not in ua:
        browser = 'Safari'
    elif 'firefox' in ua:
        browser = 'Firefox'
    elif 'edge' in ua or 'edg' in ua:
        browser = 'Edge'
    elif 'opera' in ua or 'opr' in ua:
        browser = 'Opera'
    else:
        browser = 'Other'

    if 'windows' in ua:
        os = 'Windows'
    elif 'macintosh' in ua or 'mac os' in ua:
        os = 'macOS'
    elif 'iphone' in ua or 'ipad' in ua:
        os = 'iOS'
    elif 'android' in ua:
        os = 'Android'
    elif 'linux' in ua:
        os = 'Linux'
    else:
        os = 'Other'

    return device_type, browser, os


import threading
import ipaddress
from main.utils import run_async

def get_ip_location(ip, session_key=None):
    if not ip:
        return 'Unknown'
        
    ip_clean = ip.strip()
    if ip_clean.startswith('::ffff:'):
        ip_clean = ip_clean[7:]
        
    if ip_clean in ('::1', 'localhost', '127.0.0.1'):
        return 'Local / Development'
        
    try:
        ip_obj = ipaddress.ip_address(ip_clean)
        if ip_obj.is_private or ip_obj.is_loopback:
            return 'Local / Development'
    except Exception:
        pass

    cached_loc = cache.get(f'ip_loc_{ip_clean}')
    if cached_loc:
        return cached_loc

    if session_key:
        def fetch_location():
            try:
                url = f"http://ip-api.com/json/{ip_clean}?fields=country,city,status"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('status') == 'success':
                        country = data.get('country', '')
                        city = data.get('city', '')
                        loc = f"{city}, {country}" if country and city else (country or 'Unknown')
                        cache.set(f'ip_loc_{ip_clean}', loc, 86400)
                        UserSession.objects.filter(session_key=session_key).update(location=loc)
            except Exception:
                pass
        
        run_async(fetch_location)
        return 'Retrieving...'

    try:
        url = f"http://ip-api.com/json/{ip_clean}?fields=country,city,status"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'success':
                country = data.get('country', '')
                city = data.get('city', '')
                loc = f"{city}, {country}" if country and city else (country or 'Unknown')
                cache.set(f'ip_loc_{ip_clean}', loc, 86400)
                return loc
    except Exception:
        pass

    return 'Unknown'


class TimezoneMiddleware:
    """
    Har bir so'rov uchun O'zbekiston (Asia/Tashkent UTC+5) vaqt mintaqasini faollashtiradi.
    Bu shablonlar ({{ date|date }}), formalar va barcha view'larda vaqt O'zbekiston
    vaqti bilan to'g'ri ko'rinishini kafolatlaydi.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            import zoneinfo
            self.tz = zoneinfo.ZoneInfo('Asia/Tashkent')
        except Exception:
            import pytz
            self.tz = pytz.timezone('Asia/Tashkent')

    def __call__(self, request):
        timezone.activate(self.tz)
        return self.get_response(request)


class NoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            path = request.path
            if not (path.startswith('/static/') or path.startswith('/media/')):
                add_never_cache_headers(response)
        return response


class SessionDeviceTrackerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith('/static/') or path.startswith('/media/') or any(path.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.css', '.js']):
            return self.get_response(request)

        if request.user.is_authenticated:
            session_key = request.session.session_key
            if session_key:
                # Throttle DB updates per session key (update DB at most once per 60 seconds)
                throttle_cache_key = f'session_tracked_{session_key}'
                if not cache.get(throttle_cache_key):
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip = x_forwarded_for.split(',')[0].strip()
                    else:
                        ip = request.META.get('REMOTE_ADDR')

                    ua_string = request.META.get('HTTP_USER_AGENT', '')
                    device_type, browser, os = parse_user_agent(ua_string)

                    existing = UserSession.objects.filter(session_key=session_key).first()
                    if existing and existing.ip_address == ip and existing.location not in ('Unknown', 'Retrieving...'):
                        location = existing.location
                    else:
                        location = get_ip_location(ip, session_key=session_key)

                    UserSession.objects.update_or_create(
                        session_key=session_key,
                        defaults={
                            'user': request.user,
                            'ip_address': ip,
                            'user_agent': ua_string,
                            'device_type': device_type,
                            'browser': browser,
                            'os': os,
                            'location': location,
                            'last_activity': timezone.now(),
                            'is_active': True
                        }
                    )

                    # Periodically clean inactive sessions (throttled)
                    cutoff = timezone.now() - timezone.timedelta(seconds=18000)
                    UserSession.objects.filter(last_activity__lt=cutoff).update(is_active=False)

                    cache.set(throttle_cache_key, True, 60)

        response = self.get_response(request)
        return response


class ErrorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        
        # Allow superusers, staff, and admin role to bypass locks
        user = request.user
        is_privileged = user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin')
        
        if not is_privileged and not self.is_whitelisted(path):
            from main.models import LockedPage
            if LockedPage.objects.filter(url_path=path, is_active=True).exists():
                from django.shortcuts import render
                return render(request, 'locked_page.html', status=503)
                
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        import traceback
        from main.models import SystemErrorLog, LockedPage
        
        user = request.user if request.user and request.user.is_authenticated else None
        tb_str = traceback.format_exc()
        
        SystemErrorLog.objects.create(
            user=user,
            url_path=request.path,
            error_message=str(exception),
            traceback=tb_str
        )
        
        path = request.path
        if not self.is_whitelisted(path):
            LockedPage.objects.update_or_create(
                url_path=path,
                defaults={
                    'reason': f"Kutilmagan xatolik yuz berdi: {str(exception)}",
                    'is_active': False  # Softened: Do not block users automatically. Admins can lock manually if needed.
                }
            )
        return None

    def is_whitelisted(self, path):
        if path.startswith('/admin/'):
            return True
        for w in [
            '/login',
            '/logout',
            '/adminpanel/dashboard',
            '/adminpanel/error-logs',
            '/adminpanel/locked-pages',
            '/static/',
            '/media/',
        ]:
            if path.startswith(w):
                return True
        return False
