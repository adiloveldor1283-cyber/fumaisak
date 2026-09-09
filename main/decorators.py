from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden, JsonResponse

def role_required(allowed_roles):
    """
    Decorator for views that checks if the user is authenticated and has one of the allowed roles
    (or is superuser or staff).
    Handles both HTML redirect requests and AJAX/API requests.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/adminpanel/api/'):
                    return JsonResponse({'status': 'error', 'message': "Ruxsat berilmagan. Iltimos tizimga kiring."}, status=401)
                return redirect('login')

            user = request.user
            # Superuser and staff have all privileges by default
            if user.is_superuser or user.is_staff or user.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/adminpanel/api/'):
                return JsonResponse({'status': 'error', 'message': "Ruxsat berilmagan. Sizda yetarli huquqlar yo'q."}, status=403)
            return HttpResponseForbidden("Sizda ushbu sahifaga kirish huquqi yo'q!")

        return _wrapped_view
    return decorator

def admin_required(view_func):
    """
    Shortcut for views that only superusers, staff, or users with role='admin' can access.
    """
    return role_required(['admin'])(view_func)


def subadmin_permission_required(permission_name):
    """
    Decorator for views that checks if the user is authenticated and has the specific sub-admin permission.
    Superusers, staff, and users with role='admin' have access by default.
    Users with role='reception' have access if the permission_name is in their subadmin_permissions.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/adminpanel/api/'):
                    return JsonResponse({'status': 'error', 'message': "Ruxsat berilmagan. Iltimos tizimga kiring."}, status=401)
                return redirect('login')

            user = request.user
            if user.is_superuser or user.is_staff or user.role == 'admin':
                return view_func(request, *args, **kwargs)

            if user.role == 'reception':
                perms = getattr(user, 'subadmin_permissions', None)
                if isinstance(perms, list) and permission_name in perms:
                    return view_func(request, *args, **kwargs)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/adminpanel/api/'):
                return JsonResponse({'status': 'error', 'message': "Ruxsat berilmagan. Sizda yetarli huquqlar yo'q."}, status=403)
            return HttpResponseForbidden("Sizda ushbu sahifaga kirish huquqi yo'q!")

        return _wrapped_view
    return decorator

