import time
import requests
from django.core.management.base import BaseCommand
from django.core.cache import cache
from main.telegram_service import get_bot_token, send_telegram_message
from main.sms_service import clean_phone_number, generate_otp_code
from main.models import CustomUser
from django.db.models import Q

class Command(BaseCommand):
    help = 'Runs the Telegram Bot in polling mode for local development'

    def handle(self, *args, **options):
        token = get_bot_token()
        if not token:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN not configured!'))
            return

        self.stdout.write(self.style.SUCCESS("Starting Telegram Bot in POLLING mode..."))
        self.stdout.write(self.style.WARNING("Press Ctrl+C to stop."))
        
        # Delete webhook first to allow polling
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
                    text = (message.get('text') or '').strip()
                    contact = message.get('contact')
                    
                    # 1. Check if chat is already linked to an existing user
                    linked_user = CustomUser.objects.filter(telegram_chat_id=str(chat_id)).first()
                    
                    # 2. Handle Contact Sharing (Button clicked: request_contact)
                    if contact:
                        raw_phone = contact.get('phone_number', '')
                        phone_clean = clean_phone_number(raw_phone)
                        
                        if phone_clean:
                            # Save chat_id mapped to phone in cache
                            cache.set(f"tg_chat_by_phone_{phone_clean}", str(chat_id), timeout=7200)
                            
                            # Check if user already exists in DB
                            existing_user = CustomUser.objects.filter(
                                Q(phone_number=raw_phone) |
                                Q(phone_number=f"+{phone_clean}") |
                                Q(phone_number=phone_clean) |
                                Q(phone_number__endswith=phone_clean[3:])
                            ).first()
                            
                            if existing_user:
                                existing_user.telegram_chat_id = str(chat_id)
                                existing_user.telegram_token = None
                                existing_user.telegram_otp_code = None
                                existing_user.telegram_otp_created_at = None
                                existing_user.save()
                                
                                remove_kb = {"remove_keyboard": True}
                                welcome_msg = (
                                    f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                                    f"Salom, <b>{existing_user.first_name or existing_user.username}</b>!\n"
                                    f"Sizning profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi.\n"
                                    f"Endi dars jadvallari, to'lov cheklari va muhim bildirishnomalar shu yerga keladi. 🚀"
                                )
                                send_telegram_message(str(chat_id), welcome_msg, reply_markup=remove_kb)
                                self.stdout.write(self.style.SUCCESS(f"Linked existing user by contact: {existing_user.username} (Chat ID: {chat_id})"))
                            else:
                                # Generate Registration OTP for Admin Panel
                                otp_code = generate_otp_code()
                                cache_payload = {
                                    'otp': otp_code,
                                    'chat_id': str(chat_id),
                                    'phone_clean': phone_clean,
                                    'created_at': time.time(),
                                    'expires_at': time.time() + 600
                                }
                                cache.set(f"tg_reg_otp_{phone_clean}", cache_payload, timeout=600)
                                
                                remove_kb = {"remove_keyboard": True}
                                otp_msg = (
                                    f"✅ <b>Telefon raqamingiz qabul qilindi:</b> +{phone_clean}\n\n"
                                    f"🔢 <b>Sizning ro'yxatdan o'tish kodingiz:</b> <code>{otp_code}</code>\n"
                                    f"⏳ <i>Amal qilish muddati: 10 daqiqa</i>\n\n"
                                    f"Ushbu kodni markaz administratoriga ayting. Administrator ro'yxatdan o'tkazgach, "
                                    f"tizimga kirish uchun login va parolingiz shu yerga yuboriladi! 🚀"
                                )
                                send_telegram_message(str(chat_id), otp_msg, reply_markup=remove_kb)
                                self.stdout.write(self.style.SUCCESS(f"Generated Reg OTP {otp_code} for phone +{phone_clean} (Chat ID: {chat_id})"))
                        continue

                    # 3. Handle /start command
                    if text.startswith('/start'):
                        parts = text.split()
                        if len(parts) == 2 and parts[1].startswith('tg_'):
                            token_val = parts[1]
                            user = CustomUser.objects.filter(telegram_token=token_val).first()
                            if user:
                                user.telegram_chat_id = str(chat_id)
                                user.telegram_token = None
                                user.telegram_otp_code = None
                                user.telegram_otp_created_at = None
                                user.save()
                                remove_kb = {"remove_keyboard": True}
                                welcome_msg = (
                                    f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                                    f"Salom, <b>{user.first_name or user.username}</b>!\n"
                                    f"Profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi.\n"
                                    f"Endi tizimdagi xabarlarni shu yerda olasiz."
                                )
                                send_telegram_message(str(chat_id), welcome_msg, reply_markup=remove_kb)
                                self.stdout.write(self.style.SUCCESS(f"Linked user via token: {user.username} (Chat ID: {chat_id})"))
                                continue

                        if linked_user:
                            already_msg = (
                                f"<b>Siz tizimga bog'langansiz!</b> ✅\n\n"
                                f"Salom, <b>{linked_user.first_name or linked_user.username}</b>!\n"
                                f"Siz ushbu Telegram hisobi orqali tizimga muvaffaqiyatli bog'langansiz va bildirishnomalarni qabul qilyapsiz."
                            )
                            send_telegram_message(str(chat_id), already_msg)
                        else:
                            contact_kb = {
                                "keyboard": [
                                    [{"text": "📱 Telefon raqamimni ulashish", "request_contact": True}]
                                ],
                                "resize_keyboard": True,
                                "one_time_keyboard": True
                            }
                            prompt_msg = (
                                f"<b>Assalomu alaykum!</b> 👋\n\n"
                                f"O'quv markazimizning rasmiy botiga xush kelibsiz.\n\n"
                                f"Tizimda ro'yxatdan o'tish yoki profilingizni bog'lash uchun quyidagi "
                                f"<b>'📱 Telefon raqamimni ulashish'</b> tugmasini bosing:"
                            )
                            send_telegram_message(str(chat_id), prompt_msg, reply_markup=contact_kb)
                        continue

                    # 4. Handle 6-digit OTP typed manually by user
                    if text.isdigit() and len(text) == 6:
                        if linked_user:
                            send_telegram_message(str(chat_id), "Siz tizimga bog'langansiz! ✅")
                        else:
                            from django.utils import timezone
                            user = CustomUser.objects.filter(telegram_otp_code=text).first()
                            if user:
                                if user.telegram_otp_created_at:
                                    time_diff = timezone.now() - user.telegram_otp_created_at
                                    if time_diff.total_seconds() <= 120:
                                        user.telegram_chat_id = str(chat_id)
                                        user.telegram_otp_code = None
                                        user.telegram_otp_created_at = None
                                        user.save()
                                        
                                        remove_kb = {"remove_keyboard": True}
                                        welcome_msg = (
                                            f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                                            f"Salom, <b>{user.first_name or user.username}</b>!\n"
                                            f"Profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi.\n"
                                            f"Endi tizimdagi xabarlarni shu yerda olasiz."
                                        )
                                        send_telegram_message(str(chat_id), welcome_msg, reply_markup=remove_kb)
                                        self.stdout.write(self.style.SUCCESS(f"Linked user by OTP: {user.username} (Chat ID: {chat_id})"))
                                    else:
                                        send_telegram_message(str(chat_id), "❌ Kodning amal qilish muddati tugagan. Iltimos qaytadan yangi kod shakllantiring.")
                                else:
                                    send_telegram_message(str(chat_id), "❌ Ulanish kodi faollashtirilmagan. Iltimos qaytadan kod shakllantiring.")
                            else:
                                send_telegram_message(str(chat_id), "❌ Kiritilgan ulanish kodi noto'g'ri. Iltimos tekshirib qaytadan kiriting.")
                    else:
                        if not linked_user:
                            contact_kb = {
                                "keyboard": [
                                    [{"text": "📱 Telefon raqamimni ulashish", "request_contact": True}]
                                ],
                                "resize_keyboard": True,
                                "one_time_keyboard": True
                            }
                            send_telegram_message(
                                str(chat_id),
                                "Ro'yxatdan o'tish yoki hisobingizni bog'lash uchun quyidagi <b>'📱 Telefon raqamimni ulashish'</b> tugmasini bosing:",
                                reply_markup=contact_kb
                            )
                        
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS("Polling stopped."))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error during polling: {str(e)}"))
                time.sleep(5)
