import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from main.telegram_service import get_bot_token

class Command(BaseCommand):
    help = 'Sets the Telegram Bot webhook URL'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='The base public URL of your application (e.g. https://my-domain.com)')

    def handle(self, *args, **options):
        base_url = options['url'].rstrip('/')
        token = get_bot_token()
        
        if not token:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN environment variable is not configured in .env!'))
            return
            
        webhook_url = f"{base_url}/telegram/webhook/"
        telegram_api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        
        self.stdout.write(self.style.WARNING(f"Setting Telegram Webhook to: {webhook_url}..."))
        
        try:
            response = requests.post(telegram_api_url, data={'url': webhook_url}, timeout=10)
            result = response.json()
            if result.get('ok'):
                self.stdout.write(self.style.SUCCESS(f"Success: Webhook successfully set to {webhook_url}"))
                self.stdout.write(self.style.SUCCESS(f"Telegram response: {result.get('description')}"))
            else:
                self.stdout.write(self.style.ERROR(f"Error: {result.get('description')}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to connect to Telegram API: {str(e)}"))
