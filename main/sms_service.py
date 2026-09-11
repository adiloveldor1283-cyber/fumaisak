import logging
import re
import secrets
import string
import requests
from django.core.cache import cache
from main.models import SiteSetting

logger = logging.getLogger(__name__)

ESKIZ_BASE_URL = "https://notify.eskiz.uz/api"


def clean_phone_number(phone: str) -> str:
    """
    Tozalaydi va O'zbekiston raqamini 998XXXXXXXXX formatga keltiradi.
    Namuna: "+998 (90) 123-45-67" -> "998901234567"
    """
    if not phone:
        return ""
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('998') and len(digits) == 12:
        return digits
    elif len(digits) == 9:
        return f"998{digits}"
    elif digits.startswith('8') and len(digits) == 10:
        return f"998{digits[1:]}"
    return digits


def get_eskiz_settings():
    """
    SiteSetting dan Eskiz ma'lumotlarini oladi.
    """
    setting = SiteSetting.objects.first()
    if not setting:
        return None
    return {
        'email': setting.eskiz_email,
        'password': setting.eskiz_password,
        'from_name': setting.eskiz_from_name or "4546",
        'enabled': setting.sms_enabled,
        'on_register': setting.sms_on_register,
        'on_payment': setting.sms_on_payment,
        'on_absence': setting.sms_on_absence,
    }


def get_eskiz_token(force_refresh=False):
    """
    Eskiz.uz API Bearer tokenini keshdan oladi yoki yangitdan login qilib saqlaydi.
    Token 25 kun davomida keshda saqlanadi.
    """
    cache_key = "eskiz_api_bearer_token"
    if not force_refresh:
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token

    settings = get_eskiz_settings()
    if not settings or not settings['email'] or not settings['password']:
        logger.warning("Eskiz.uz Email yoki Yashirin kalit kiritilmagan.")
        return None

    try:
        url = f"{ESKIZ_BASE_URL}/auth/login"
        payload = {
            'email': settings['email'].strip(),
            'password': settings['password'].strip()
        }
        response = requests.post(url, data=payload, timeout=10)
        res_data = response.json()

        if response.status_code == 200 and 'data' in res_data and 'token' in res_data['data']:
            token = res_data['data']['token']
            cache.set(cache_key, token, 2160000)
            return token
        else:
            logger.error(f"Eskiz login xatolik: {res_data}")
            return None
    except Exception as e:
        logger.error(f"Eskiz auth request xatolik: {e}")
        return None


def send_sms(phone: str, message: str, from_name: str = None, check_enabled: bool = True):
    """
    Eskiz.uz orqali SMS yuborish funksiyasi.
    Qaytaradi: {'success': bool, 'message': str, 'status_code': int, 'raw': dict}
    """
    settings = get_eskiz_settings()
    if check_enabled and (not settings or not settings.get('enabled')):
        return {
            'success': False,
            'message': "SMS xizmati tizim sozlamalarida o'chirilgan."
        }

    clean_phone = clean_phone_number(phone)
    if not clean_phone or len(clean_phone) != 12:
        return {
            'success': False,
            'message': f"Telefon raqami noto'g'ri: {phone}"
        }

    token = get_eskiz_token()
    if not token:
        return {
            'success': False,
            'message': "Eskiz.uz tizimiga ulanib bo'lmadi. Email va Yashirin kalitni tekshiring."
        }

    sender = from_name or (settings.get('from_name') if settings else "4546") or "4546"

    def _execute_send(auth_token):
        url = f"{ESKIZ_BASE_URL}/message/sms/send"
        headers = {
            'Authorization': f"Bearer {auth_token}"
        }
        payload = {
            'mobile_phone': clean_phone,
            'message': message,
            'from': sender
        }
        return requests.post(url, headers=headers, data=payload, timeout=12)

    try:
        response = _execute_send(token)

        if response.status_code == 401:
            token = get_eskiz_token(force_refresh=True)
            if token:
                response = _execute_send(token)

        res_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'text': response.text}

        if response.status_code == 200 and res_data.get('status') == 'waiting':
            return {
                'success': True,
                'message': "SMS muvaffaqiyatli yuborildi.",
                'raw': res_data
            }
        else:
            err_msg = res_data.get('message') or res_data.get('error') or f"Status: {response.status_code}"
            return {
                'success': False,
                'message': f"SMS yuborishda xatolik: {err_msg}",
                'raw': res_data
            }
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'message': "Eskiz serveriga ulanish vaqti tugadi (Timeout)."
        }
    except Exception as e:
        logger.error(f"SMS send xatolik: {e}")
        return {
            'success': False,
            'message': f"SMS yuborishda kutilmagan xatolik: {str(e)}"
        }


def get_eskiz_balance():
    """
    Eskiz.uz foydalanuvchi balansi va SMS limitini oladi.
    """
    token = get_eskiz_token()
    if not token:
        return {
            'success': False,
            'message': "Eskiz.uz tizimiga ulanib bo'lmadi."
        }

    try:
        url = f"{ESKIZ_BASE_URL}/auth/user"
        headers = {'Authorization': f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 401:
            token = get_eskiz_token(force_refresh=True)
            if token:
                response = requests.get(url, headers={'Authorization': f"Bearer {token}"}, timeout=10)

        res_data = response.json()
        if response.status_code == 200 and 'data' in res_data:
            user_data = res_data['data']
            return {
                'success': True,
                'name': user_data.get('name'),
                'email': user_data.get('email'),
                'balance': user_data.get('balance', 0),
                'role': user_data.get('role'),
                'raw': user_data
            }
        return {
            'success': False,
            'message': res_data.get('message', 'Balansni olib bo\'lmadi.')
        }
    except Exception as e:
        return {
            'success': False,
            'message': f"Balansni tekshirishda xatolik: {str(e)}"
        }


def generate_otp_code() -> str:
    """
    6 xonali xavfsiz tasdiqlash kodini generatsiya qiladi.
    """
    return f"{secrets.randbelow(900000) + 100000}"


def generate_random_password(length: int = 8) -> str:
    """
    O'quvchi va o'qituvchi uchun xavfsiz va eslab qolish oson parol generatsiya qiladi.
    Namuna: 'Dev84921' yoki 'Abc78912'
    """
    letters = "".join(secrets.choice(string.ascii_letters) for _ in range(4))
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"{letters.capitalize()}{digits}"
