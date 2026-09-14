from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env()

# Quick-start development settings - unsuitable for production
SECRET_KEY = env('SECRET_KEY', default='django-insecure-fumaisak-production-key-change-later-1283')
GEMINI_API_KEY = env('GEMINI_API_KEY', default=None)
TELEGRAM_BOT_TOKEN = env('TELEGRAM_BOT_TOKEN', default=None)
TELEGRAM_BOT_USERNAME = env('TELEGRAM_BOT_USERNAME', default=None)
TELEGRAM_WEBHOOK_SECRET_TOKEN = env('TELEGRAM_WEBHOOK_SECRET_TOKEN', default=None)

# DEBUG statusni .env fayldan o'qiymiz (default True)
DEBUG = env.bool('DEBUG', default=True)

# Ruxsat etilgan xostlar
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['lms.upcode.uz', '*'])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'https://api.upcode.uz',
    'https://lms.upcode.uz',
    'http://lms.upcode.uz',
    'https://*.upcode.uz',
    'http://*.upcode.uz',
    'https://*.railway.app',
    'https://*.up.railway.app',
    'https://*.netlify.app',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
])

# Application definition
INSTALLED_APPS = [
    "unfold",  # Must be first
    "unfold.contrib.import_export",  # Import/Export styling integration
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main',
    'import_export',
]

from django.urls import reverse_lazy

UNFOLD = {
    "SITE_TITLE": "DjangoProject.utils.get_admin_site_title",
    "SITE_HEADER": "DjangoProject.utils.get_admin_site_header",
    "SITE_SUBHEADER": "DjangoProject.utils.get_admin_site_subheader",
    "SITE_ICON": "DjangoProject.utils.get_admin_site_icon",
    "THEME": "dark",  # default to dark theme
    "SHOW_HISTORY": True,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Foydalanuvchilar va Guruhlar",
                "separator": True,
                "items": [
                    {"title": "Foydalanuvchilar (Xodimlar/O'quvchilar)", "icon": "people", "link": reverse_lazy("admin:main_customuser_changelist")},
                    {"title": "Guruhlar", "icon": "groups", "link": reverse_lazy("admin:main_group_changelist")},
                    {"title": "Guruh a'zoligi", "icon": "group_add", "link": reverse_lazy("admin:main_groupstudentmembership_changelist")},
                    {"title": "Dars jadvali", "icon": "calendar_month", "link": reverse_lazy("admin:main_schedule_changelist")},
                    {"title": "Davomat", "icon": "fact_check", "link": reverse_lazy("admin:main_attendance_changelist")},
                    {"title": "Telegram Bot kontaktlari", "icon": "send", "link": reverse_lazy("admin:main_telegrambotcontact_changelist")},
                    {"title": "Faol seanslar (Qurilmalar)", "icon": "devices", "link": reverse_lazy("admin:main_usersession_changelist")},
                ],
            },
            {
                "title": "Fanlar, Darslar va O'quv Materiallari",
                "separator": True,
                "items": [
                    {"title": "Fanlar", "icon": "subject", "link": reverse_lazy("admin:main_subject_changelist")},
                    {"title": "Fan materiallari", "icon": "folder", "link": reverse_lazy("admin:main_subjectmaterial_changelist")},
                    {"title": "Dars kundaligi", "icon": "menu_book", "link": reverse_lazy("admin:main_grouplesson_changelist")},
                    {"title": "Kitoblar kutubxonasi", "icon": "auto_stories", "link": reverse_lazy("admin:main_book_changelist")},
                    {"title": "Video darslar", "icon": "video_library", "link": reverse_lazy("admin:main_groupvideo_changelist")},
                    {"title": "Vazifalar", "icon": "assignment", "link": reverse_lazy("admin:main_assignment_changelist")},
                    {"title": "Topshirilgan vazifalar", "icon": "assignment_turned_in", "link": reverse_lazy("admin:main_assignmentsubmission_changelist")},
                ],
            },
            {
                "title": "Moliya, To'lovlar va Hamyon",
                "separator": True,
                "items": [
                    {"title": "Guruh to'lov tariflari", "icon": "price_change", "link": reverse_lazy("admin:main_grouppaymentinfo_changelist")},
                    {"title": "O'quvchilar to'lovlari", "icon": "receipt_long", "link": reverse_lazy("admin:main_studentpayment_changelist")},
                    {"title": "O'qituvchi oylik to'lovlari", "icon": "payments", "link": reverse_lazy("admin:main_teachersalarypayment_changelist")},
                    {"title": "Virtual hamyon operatsiyalari", "icon": "account_balance_wallet", "link": reverse_lazy("admin:main_wallettransaction_changelist")},
                    {"title": "Onlayn buyurtmalar", "icon": "shopping_cart", "link": reverse_lazy("admin:main_paymentorder_changelist")},
                    {"title": "Payme tranzaksiyalari", "icon": "credit_card", "link": reverse_lazy("admin:main_paymetransaction_changelist")},
                    {"title": "Click tranzaksiyalari", "icon": "payment", "link": reverse_lazy("admin:main_clicktransaction_changelist")},
                ],
            },
            {
                "title": "Testlar va Imtihonlar (DTM & AI)",
                "separator": True,
                "items": [
                    {"title": "Guruh testlari (Quiz)", "icon": "quiz", "link": reverse_lazy("admin:main_quiz_changelist")},
                    {"title": "Test savollari", "icon": "help_outline", "link": reverse_lazy("admin:main_question_changelist")},
                    {"title": "Test natijalari", "icon": "assessment", "link": reverse_lazy("admin:main_studentquizresult_changelist")},
                    {"title": "DTM Imtihonlar", "icon": "history_edu", "link": reverse_lazy("admin:main_dtmexam_changelist")},
                    {"title": "DTM Ro'yxatdan o'tganlar", "icon": "app_registration", "link": reverse_lazy("admin:main_dtmregistration_changelist")},
                    {"title": "DTM Savollar banki", "icon": "inventory_2", "link": reverse_lazy("admin:main_dtmquestionpool_changelist")},
                    {"title": "DTM Test natijalari", "icon": "grade", "link": reverse_lazy("admin:main_studentdtmexamresult_changelist")},
                    {"title": "AI Individual testlar", "icon": "smart_toy", "link": reverse_lazy("admin:main_aiquiz_changelist")},
                    {"title": "AI Test savollari", "icon": "psychology", "link": reverse_lazy("admin:main_aiquestion_changelist")},
                    {"title": "AI O'quv rejalari", "icon": "insights", "link": reverse_lazy("admin:main_studentaiplan_changelist")},
                ],
            },
            {
                "title": "Tizim va Xavfsizlik Sozlamalari",
                "separator": True,
                "items": [
                    {"title": "Logotip, SMS & Bot Sozlamalari", "icon": "settings", "link": reverse_lazy("admin:main_sitesetting_changelist")},
                    {"title": "Profil rasmlari sozlamasi", "icon": "manage_accounts", "link": reverse_lazy("admin:main_profilesetting_changelist")},
                    {"title": "Tizim e'lonlari", "icon": "campaign", "link": reverse_lazy("admin:main_systemannouncement_changelist")},
                    {"title": "Audit loglar (Harakatlar)", "icon": "security", "link": reverse_lazy("admin:main_auditlog_changelist")},
                    {"title": "Xatoliklar jurnali (Error logs)", "icon": "bug_report", "link": reverse_lazy("admin:main_systemerrorlog_changelist")},
                    {"title": "Bloklangan sahifalar", "icon": "lock", "link": reverse_lazy("admin:main_lockedpage_changelist")},
                    {"title": "Monitoring API kalitlari", "icon": "key", "link": reverse_lazy("admin:main_monitoringapikey_changelist")},
                ],
            },
        ],
    },
}


import dj_database_url

MIDDLEWARE = [
    'main.middleware.MonitoringCorsMiddleware',  # Must be at the very top to handle API & preflights
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'main.middleware.TimezoneMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'main.middleware.NoCacheMiddleware',
    'main.middleware.SessionDeviceTrackerMiddleware',
    'main.middleware.OnboardingRequiredMiddleware',
    'main.middleware.ErrorTrackingMiddleware',
]

ROOT_URLCONF = 'DjangoProject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "main" / "templates"],  # umumiy templates papkani ulash
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'main.context_processors.all_student_notifications',
                'main.context_processors.teacher_notifications',
                'main.context_processors.site_images',
                'main.context_processors.system_announcements',
                'main.context_processors.error_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'DjangoProject.wsgi.application'

# ✅ PostgreSQL DATABASES: Local yoki Railway (DATABASE_URL)
DATABASE_URL = env('DATABASE_URL', default=None)
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': env('DB_ENGINE', default='django.db.backends.postgresql'),
            'NAME': env('DB_NAME', default='fumaisak_db'),
            'USER': env('DB_USER', default='postgres'),
            'PASSWORD': env('DB_PASSWORD', default='123456'),
            'HOST': env('DB_HOST', default='127.0.0.1'),
            'PORT': env('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 600,
        }
    }

# Parol validatsiya
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Til va vaqt
LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True
FORMAT_MODULE_PATH = [
    'DjangoProject.formats',
]

# Static fayllar
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
_STATIC_DIR = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [_STATIC_DIR] if os.path.exists(_STATIC_DIR) else []

# ✅ WhiteNoise static storage
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'main.CustomUser'

# ==============================================================================
# 📂 MEDIA & RAILWAY VOLUME SOZLAMALARI
# ==============================================================================
MEDIA_URL = '/media/'

# Railway volume ulanish yo'llari:
# 1. Custom env MEDIA_ROOT (masalan, /app/media yoki /data/media)
# 2. RAILWAY_VOLUME_MOUNT_PATH muhit o'zgaruvchisi
# 3. Standart BASE_DIR / 'media'
_railway_vol = env('RAILWAY_VOLUME_MOUNT_PATH', default=None)
if _railway_vol and os.path.exists(_railway_vol):
    _default_media_root = _railway_vol
else:
    _default_media_root = os.path.join(BASE_DIR, 'media')

MEDIA_ROOT = env('MEDIA_ROOT', default=_default_media_root)

# Papkalarni avtomatik yaratish (Permission va yo'l xatolarining oldini olish uchun)
try:
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    for _sub in ['profiles', 'subject_materials', 'books', 'assignments', 'submissions', 'videos']:
        os.makedirs(os.path.join(MEDIA_ROOT, _sub), exist_ok=True)
except Exception:
    pass

LOGIN_URL = 'login'

# Xavfsizlik sarlavhalari (Production / DEBUG=False rejimida faollashadi)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

X_FRAME_OPTIONS = 'SAMEORIGIN'

# Avtomatik seans o'chish sozlamalari (5 soat)
SESSION_COOKIE_AGE = 18000
SESSION_SAVE_EVERY_REQUEST = False

# High-concurrency cached_db sessiya tizimi (Xotira keshidan birinchi o'qiydi, DB ga ortiqcha yozmaydi)
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# Kesh tizimi sozlamalari (Local Memory Cache - Concurrency optimizatsiyasi uchun)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fumaisak-cache-store',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 10000
        }
    }
}

# ==============================================================================
# 💳 ONLINE TO'LOV SHLYUZLARI SOZLAMALARI (PAYME & CLICK)
# ==============================================================================
ONLINE_PAYMENTS_ENABLED = env.bool('ONLINE_PAYMENTS_ENABLED', default=False)
PAYME_MERCHANT_ID = env('PAYME_MERCHANT_ID', default='')
PAYME_SECRET_KEY = env('PAYME_SECRET_KEY', default='')
PAYME_TEST_MODE = env.bool('PAYME_TEST_MODE', default=True)

CLICK_SERVICE_ID = env('CLICK_SERVICE_ID', default='')
CLICK_MERCHANT_ID = env('CLICK_MERCHANT_ID', default='')
CLICK_SECRET_KEY = env('CLICK_SECRET_KEY', default='')
CLICK_MERCHANT_USER_ID = env('CLICK_MERCHANT_USER_ID', default='')
CLICK_TEST_MODE = env.bool('CLICK_TEST_MODE', default=True)


