import html
import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def get_telegram_settings():
    """
    Retrieves Telegram Bot settings from SiteSetting, settings.py, or environment.
    """
    token = None
    username = None
    enabled = True
    on_register = True
    on_payment = True
    on_absence = True

    try:
        from main.models import SiteSetting
        site_setting = SiteSetting.objects.first()
        if site_setting:
            if site_setting.telegram_bot_token:
                token = site_setting.telegram_bot_token.strip()
            if site_setting.telegram_bot_username:
                username = site_setting.telegram_bot_username.strip().replace('@', '')
            enabled = site_setting.telegram_enabled
            on_register = site_setting.telegram_on_register
            on_payment = site_setting.telegram_on_payment
            on_absence = site_setting.telegram_on_absence
    except Exception:
        pass

    if not token:
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not username:
        username = (getattr(settings, 'TELEGRAM_BOT_USERNAME', None) or os.environ.get('TELEGRAM_BOT_USERNAME', 'FumaIsakBot')).replace('@', '')

    return {
        'token': token,
        'username': username,
        'enabled': enabled,
        'on_register': on_register,
        'on_payment': on_payment,
        'on_absence': on_absence
    }

def get_bot_token():
    return get_telegram_settings()['token']

def get_bot_username():
    return get_telegram_settings()['username']

def send_telegram_message(chat_id, text, parse_mode='HTML', reply_markup=None):
    """
    Sends a text message to a Telegram chat using requests.
    Supports HTML formatting, optional reply_markup, and automatic plain-text fallback.
    """
    tg_config = get_telegram_settings()
    token = tg_config['token']
    if not token or not chat_id:
        logger.warning("Telegram Warning: Bot token or chat_id not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': str(chat_id),
        'text': text,
    }
    if parse_mode:
        payload['parse_mode'] = parse_mode
    if reply_markup:
        payload['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=payload, timeout=8)
        response_data = response.json()
        if response_data.get('ok'):
            return True
        else:
            logger.warning(f"Telegram Error Response: {response_data}")
            # If HTML parsing failed, retry as plain text without parse_mode
            if parse_mode:
                # Strip simple HTML tags for fallback
                import re
                plain_text = re.sub(r'<[^>]*>', '', text)
                retry_payload = {
                    'chat_id': str(chat_id),
                    'text': plain_text,
                }
                if reply_markup:
                    retry_payload['reply_markup'] = reply_markup
                retry_resp = requests.post(url, json=retry_payload, timeout=8)
                if retry_resp.json().get('ok'):
                    return True
            return False
    except Exception as e:
        logger.error(f"Telegram Exception: {str(e)}")
        return False

def generate_telegram_link(user):
    """
    Generates a unique linking token and Telegram bot URL for a user.
    """
    import uuid
    token = f"tg_{uuid.uuid4().hex[:16]}"
    user.telegram_token = token
    user.save()
    
    bot_username = get_bot_username()
    return f"https://t.me/{bot_username}?start={token}"

def send_telegram_registration_credentials(chat_id, username, password, login_url=None, full_name=None):
    """
    Yangi ro'yxatdan o'tgan foydalanuvchiga Telegram bot orqali login va parolni yuboradi.
    """
    safe_name = html.escape(str(full_name)) if full_name else ""
    safe_username = html.escape(str(username))
    safe_password = html.escape(str(password))
    safe_url = html.escape(str(login_url or "https://tizim.uz/login"))

    name_str = f", <b>{safe_name}</b>" if safe_name else ""
    url_str = safe_url
    
    text = (
        f"🎉 <b>Xush kelibsiz{name_str}!</b>\n\n"
        f"O'quv markazimizning o'quv tizimida profilingiz muvaffaqiyatli yaratildi.\n\n"
        f"🔐 <b>Tizimga kirish ma'lumotlaringiz:</b>\n"
        f"👤 <b>Login:</b> <code>{safe_username}</code>\n"
        f"🔑 <b>Parol:</b> <code>{safe_password}</code>\n\n"
        f"🌐 <b>Tizimga kirish manzili:</b>\n{url_str}\n\n"
        f"⚠️ <i>Xavfsizlik eslatmasi: Birinchi marta tizimga kirganingizda profilingizni to'ldiring va parolingizni o'zgartiring.</i>"
    )
    
    # Remove custom keyboard so user sees standard interface
    remove_keyboard = {"remove_keyboard": True}
    return send_telegram_message(chat_id, text, parse_mode='HTML', reply_markup=remove_keyboard)
