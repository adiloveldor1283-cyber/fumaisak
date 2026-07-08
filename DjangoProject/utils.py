from django.core.cache import cache
from django.http import HttpResponse
from functools import wraps
import time

def rate_limit(limit=5, period=60):
    """
    Simple IP-based rate limiting decorator using Django cache.
    limit: max requests allowed
    period: time window in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')

            # Create cache key based on IP and view name
            key = f"ratelimit_{view_func.__name__}_{ip}"
            
            # Get list of request timestamps for this key
            request_times = cache.get(key, [])
            now = time.time()
            
            # Filter timestamps that are outside the current window
            request_times = [t for t in request_times if now - t < period]
            
            if len(request_times) >= limit:
                return HttpResponse("Too many requests. Please try again later.", status=429)
            
            request_times.append(now)
            cache.set(key, request_times, period)
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
