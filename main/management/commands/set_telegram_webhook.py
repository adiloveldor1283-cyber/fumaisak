from django.core.management.base import BaseCommand
import requests
from django.conf import settings
from main.telegram_service import get_bot_token

class Command(BaseCommand):
    help = 'Sets the Telegram Bot webhook to the production URL'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, default='https://lms.upcode.uz', help='Custom webhook base URL (e.g. https://lms.upcode.uz)')

    def handle(self, *args, **options):
        token = get_bot_token()
        if not token:
            self.stdout.write(self.style.ERROR("TELEGRAM_BOT_TOKEN sozlanmagan!"))
            return

        base_url = options.get('url') or 'https://lms.upcode.uz'
        webhook_url = f"{base_url.rstrip('/')}/telegram/webhook/"
        
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        params = {'url': webhook_url}
        
        secret_token = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET_TOKEN', None)
        if secret_token:
            params['secret_token'] = secret_token

        try:
            res = requests.post(api_url, data=params, timeout=10).json()
            if res.get('ok'):
                self.stdout.write(self.style.SUCCESS(f"✅ Webhook muvaffaqiyatli ulandi: {webhook_url}"))
            else:
                self.stdout.write(self.style.ERROR(f"❌ Xatolik: {res}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Ulanishda xatolik: {str(e)}"))
