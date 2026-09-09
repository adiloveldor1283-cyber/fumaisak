import time
import requests
from django.core.management.base import BaseCommand
from main.telegram_service import get_bot_token, send_telegram_message
from main.models import CustomUser

class Command(BaseCommand):
    help = 'Runs the Telegram Bot in polling mode for local development'

    def handle(self, *args, **options):
        token = get_bot_token()
        if not token:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN not configured in .env!'))
            return

        self.stdout.write(self.style.SUCCESS("Starting Telegram Bot in POLLING mode..."))
        self.stdout.write(self.style.WARNING("Press Ctrl+C to stop."))
        
        # Delete webhook first to allow polling (Telegram does not allow polling while a webhook is set)
        try:
            requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=5)
            self.stdout.write(self.style.WARNING("Existing webhooks deleted to enable polling."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to delete webhook: {str(e)}"))

        offset = 0
        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {'offset': offset, 'timeout': 10}
                response = requests.get(url, params=params, timeout=15)
                
                if response.status_code != 200:
                    time.sleep(3)
                    continue
                    
                data = response.json()
                if not data.get('ok'):
                    time.sleep(3)
                    continue
                    
                updates = data.get('result', [])
                for update in updates:
                    offset = update.get('update_id') + 1
                    message = update.get('message')
                    if not message:
                        continue
                        
                    chat = message.get('chat', {})
                    chat_id = chat.get('id')
                    text = message.get('text', '').strip()
                    
                    # Check if already linked
                    linked_user = CustomUser.objects.filter(telegram_chat_id=str(chat_id)).first()
                    
                    if text.startswith('/start'):
                        parts = text.split()
                        if len(parts) == 2 and parts[1].startswith('tg_'):
                            token = parts[1]
                            user = CustomUser.objects.filter(telegram_token=token).first()
                            if user:
                                user.telegram_chat_id = str(chat_id)
                                user.telegram_token = None
                                user.telegram_otp_code = None
                                user.telegram_otp_created_at = None
                                user.save()
                                welcome_msg = (
                                    f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                                    f"Salom, {user.first_name} {user.last_name}!\n"
                                    f"Profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi (Local Polling).\n"
                                    f"Endi tizimdagi xabarlarni shu yerda olasiz."
                                )
                                send_telegram_message(str(chat_id), welcome_msg)
                                self.stdout.write(self.style.SUCCESS(f"Linked user: {user.username} via link (Chat ID: {chat_id})"))
                                continue

                        if linked_user:
                            already_msg = (
                                f"<b>Siz tizimga bog'langansiz!</b> ✅\n\n"
                                f"Salom, {linked_user.first_name} {linked_user.last_name}!\n"
                                f"Siz ushbu Telegram hisobi orqali tizimga muvaffaqiyatli bog'langansiz va bildirishnomalarni qabul qilyapsiz."
                            )
                            send_telegram_message(str(chat_id), already_msg)
                        else:
                            send_telegram_message(str(chat_id), "Salom! Profilingizni bog'lash uchun shaxsiy kabinetingizda shakllantirilgan 6 xonali ulanish kodini yuboring:")
                            
                    elif text.isdigit() and len(text) == 6:
                        if linked_user:
                            send_telegram_message(str(chat_id), "Siz tizimga bog'langansiz! ✅")
                        else:
                            from django.utils import timezone
                            user = CustomUser.objects.filter(telegram_otp_code=text).first()
                            if user:
                                if user.telegram_otp_created_at:
                                    time_diff = timezone.now() - user.telegram_otp_created_at
                                    if time_diff.total_seconds() <= 60:
                                        user.telegram_chat_id = str(chat_id)
                                        user.telegram_otp_code = None
                                        user.telegram_otp_created_at = None
                                        user.save()
                                        
                                        welcome_msg = (
                                            f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                                            f"Salom, {user.first_name} {user.last_name}!\n"
                                            f"Profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi (Local Polling).\n"
                                            f"Endi tizimdagi xabarlarni shu yerda olasiz."
                                        )
                                        send_telegram_message(str(chat_id), welcome_msg)
                                        self.stdout.write(self.style.SUCCESS(f"Linked user: {user.username} (Chat ID: {chat_id})"))
                                    else:
                                        send_telegram_message(str(chat_id), "❌ Kodning amal qilish muddati tugagan (1 daqiqa). Iltimos shaxsiy kabinetingizdan qaytadan yangi kod shakllantiring.")
                                else:
                                    send_telegram_message(str(chat_id), "❌ Ulanish kodi faollashtirilmagan. Iltimos shaxsiy kabinetingizdan qaytadan kod shakllantiring.")
                            else:
                                send_telegram_message(str(chat_id), "❌ Kiritilgan ulanish kodi noto'g'ri. Iltimos tekshirib qaytadan kiriting.")
                    else:
                        if not linked_user:
                            send_telegram_message(str(chat_id), "Salom! Profilingizni bog'lash uchun shaxsiy kabinetingizda shakllantirilgan 6 xonali ulanish kodini yuboring:")
                        
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS("Polling stopped."))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error during polling: {str(e)}"))
                time.sleep(5)
