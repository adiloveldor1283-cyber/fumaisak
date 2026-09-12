from main.models import AuditLog
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

from django.db import close_old_connections
import traceback

# Global background executor for async tasks (like sending Telegram messages)
# Increased max_workers to 30 for I/O bound Telegram requests
bg_executor = ThreadPoolExecutor(max_workers=30, thread_name_prefix="bg_tasks_")

def run_async_wrapper(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Async task error in {func.__name__}: {str(e)}\n{tb_str}")
        try:
            from main.models import SystemErrorLog
            SystemErrorLog.objects.create(
                url_path=f"Background Task: {func.__name__}",
                error_message=str(e),
                traceback=tb_str
            )
        except Exception:
            pass
    finally:
        close_old_connections()

def run_async(func, *args, **kwargs):
    """
    Submits a function to be executed in the background thread pool with DB connection cleanup.
    """
    try:
        bg_executor.submit(run_async_wrapper, func, *args, **kwargs)
    except Exception as e:
        logger.error(f"Error submitting async task: {str(e)}")

def get_client_ip(request):
    """
    Safely extract client IP from request taking proxies into account.
    """
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def log_action(user, action, description, request=None):
    """
    Log an action in the database under the AuditLog model.
    """
    ip = get_client_ip(request) if request else None

    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        description=description,
        ip_address=ip
    )

