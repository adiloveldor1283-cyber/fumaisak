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
    'https://*.railway.app',
    'https://*.up.railway.app',
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

UNFOLD = {
    "SITE_TITLE": "DjangoProject.utils.get_admin_site_title",
    "SITE_HEADER": "DjangoProject.utils.get_admin_site_header",
    "SITE_SUBHEADER": "DjangoProject.utils.get_admin_site_subheader",
    "SITE_ICON": "DjangoProject.utils.get_admin_site_icon",
    "THEME": "dark",  # default to dark theme
    "SHOW_HISTORY": True,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
}

import dj_database_url

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'main.middleware.NoCacheMiddleware',
    'main.middleware.SessionDeviceTrackerMiddleware',
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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'main.CustomUser'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

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


