from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth import login
from DjangoProject.utils import rate_limit


@rate_limit(limit=5, period=60)
def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Check if student or teacher has completed onboarding & accepted legal terms (O'RQ-547)
            if hasattr(user, 'role') and user.role in ('student', 'teacher') and not getattr(user, 'is_profile_completed', True):
                return redirect('onboarding')

            if user.is_superuser or user.is_staff or (hasattr(user, 'role') and user.role in ('admin', 'reception')):
                return redirect('admin_dashboard')
            elif hasattr(user, 'role') and user.role == 'teacher':
                return redirect('teacher_home')
            elif hasattr(user, 'role') and user.role == 'student':
                return redirect('student_home')
            else:
                messages.error(request, "Roli aniqlanmadi", extra_tags='login_message')
        else:
            messages.error(request, "Login yoki parol noto‘g‘ri", extra_tags='login_message')

    return render(request, 'login.html')


from django.http import JsonResponse

@login_required
def dismiss_announcement(request, announcement_id):
    if 'seen_announcements' not in request.session:
        request.session['seen_announcements'] = []
    
    seen_ids = request.session['seen_announcements']
    if not isinstance(seen_ids, list):
        seen_ids = list(seen_ids)
        request.session['seen_announcements'] = seen_ids
        
    if announcement_id not in seen_ids:
        seen_ids.append(announcement_id)
        request.session.modified = True
        
    return JsonResponse({'status': 'success'})


from django.contrib.auth import logout as auth_logout
from main.models import UserSession

def logout_view(request):
    session_key = request.session.session_key
    if session_key:
        UserSession.objects.filter(session_key=session_key).update(is_active=False)
    auth_logout(request)
    return redirect('login')


import json
from django.views.decorators.csrf import csrf_exempt
from main.models import CustomUser
from main.telegram_service import send_telegram_message

@csrf_exempt
def telegram_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
        
    from django.conf import settings
    secret_token = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET_TOKEN', None)
    if secret_token:
        request_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if request_token != secret_token:
            return JsonResponse({'status': 'error', 'message': "Ruxsat etilmagan webhook so'rovi."}, status=403)
        
    try:
        update = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'status': 'error', 'message': "Noto'g'ri JSON format."}, status=400)
        
    message = update.get('message')
    if not message:
        return JsonResponse({'status': 'success'})
        
    chat = message.get('chat')
    text = (message.get('text') or '').strip()
    contact = message.get('contact')
    
    if chat:
        chat_id = str(chat.get('id'))
        from django.core.cache import cache
        from main.sms_service import clean_phone_number, generate_otp_code
        from main.telegram_service import send_telegram_message
        from django.db.models import Q
        import time

        linked_user = CustomUser.objects.filter(telegram_chat_id=chat_id).first()

        # 1. Contact Sharing (Request Contact button clicked)
        if contact:
            raw_phone = contact.get('phone_number', '')
            phone_clean = clean_phone_number(raw_phone)
            if phone_clean:
                # Save chat_id mapped to phone for 24 hours
                cache.set(f"tg_chat_by_phone_{phone_clean}", chat_id, timeout=86400)

                existing_user = CustomUser.objects.filter(
                    Q(phone_number=raw_phone) |
                    Q(phone_number=f"+{phone_clean}") |
                    Q(phone_number=phone_clean) |
                    Q(phone_number__endswith=phone_clean[3:])
                ).first()

                if existing_user:
                    existing_user.telegram_chat_id = chat_id
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
                    send_telegram_message(chat_id, welcome_msg, reply_markup=remove_kb)
                else:
                    remove_kb = {"remove_keyboard": True}
                    info_msg = (
                        f"✅ <b>Telefon raqamingiz muvaffaqiyatli qabul qilindi:</b> +{phone_clean}\n\n"
                        f"Administrator sizni tizimda ro'yxatdan o'tkazayotganda, tasdiqlash kodi va tizimga kirish login/parolingiz ushbu botga yuboriladi. 🚀"
                    )
                    send_telegram_message(chat_id, info_msg, reply_markup=remove_kb)
            return JsonResponse({'status': 'success'})
        
        # 2. Start command
        if text.startswith('/start'):
            parts = text.split()
            if len(parts) == 2 and parts[1].startswith('tg_'):
                token = parts[1]
                user = CustomUser.objects.filter(telegram_token=token).first()
                if user:
                    user.telegram_chat_id = chat_id
                    user.telegram_token = None
                    user.telegram_otp_code = None
                    user.telegram_otp_created_at = None
                    user.save()
                    remove_kb = {"remove_keyboard": True}
                    welcome_msg = (
                        f"<b>Muvaffaqiyatli bog'landi!</b> ✅\n\n"
                        f"Salom, <b>{user.first_name or user.username}</b>!\n"
                        f"Profilingiz ushbu Telegram hisobiga muvaffaqiyatli bog'landi.\n"
                        f"Endi siz to'lovlar, davomat va muhim e'lonlarni bot orqali tezkor qabul qilasiz."
                    )
                    send_telegram_message(chat_id, welcome_msg, reply_markup=remove_kb)
                    return JsonResponse({'status': 'success'})

            if linked_user:
                already_msg = (
                    f"<b>Siz tizimga bog'langansiz!</b> ✅\n\n"
                    f"Salom, <b>{linked_user.first_name or linked_user.username}</b>!\n"
                    f"Siz ushbu Telegram hisobi orqali tizimga muvaffaqiyatli bog'langansiz va bildirishnomalarni qabul qilyapsiz."
                )
                send_telegram_message(chat_id, already_msg)
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
                send_telegram_message(chat_id, prompt_msg, reply_markup=contact_kb)
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
                    chat_id,
                    "Ro'yxatdan o'tish yoki hisobingizni bog'lash uchun quyidagi <b>'📱 Telefon raqamimni ulashish'</b> tugmasini bosing:",
                    reply_markup=contact_kb
                )
                
    return JsonResponse({'status': 'success'})


import io
import os
from PIL import Image, ImageDraw
from django.http import HttpResponse, Http404
from django.views.decorators.cache import cache_control
from django.core.cache import cache
from django.conf import settings
from main.models import SiteSetting

@cache_control(max_age=3600, public=True)
def circular_favicon_view(request):
    """
    Sayt logotipini to'liq dumaloq (circular) PNG favicon ko'rinishida generatsiya qiladi.
    Burchaklari shaffof (transparent alpha) bo'lib, brauzer tabida to'rtburchak emas,
    chiroyli dumaloq shaklda ko'rinadi.
    """
    cached_favicon = cache.get('circular_favicon_png')
    if cached_favicon:
        return HttpResponse(cached_favicon, content_type="image/png")

    image_path = None
    try:
        setting = SiteSetting.objects.first()
        if setting and setting.image:
            try:
                image_path = setting.image.path
            except Exception:
                pass
    except Exception:
        pass

    if not image_path or not os.path.exists(image_path):
        image_path = os.path.join(settings.BASE_DIR, 'static', 'imgs', 'images_9.webp')

    try:
        img = Image.open(image_path).convert("RGBA")
        size = min(img.size)
        left = (img.width - size) // 2
        top = (img.height - size) // 2
        img = img.crop((left, top, left + size, top + size))
        
        target_size = (128, 128)
        img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # Dumaloq niqob (Circle mask)
        mask = Image.new('L', target_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, target_size[0], target_size[1]), fill=255)
        
        output_img = Image.new('RGBA', target_size, (0, 0, 0, 0))
        output_img.paste(img, (0, 0), mask=mask)
        
        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        png_data = buf.getvalue()
        cache.set('circular_favicon_png', png_data, 86400)
        return HttpResponse(png_data, content_type="image/png")
    except Exception:
        raise Http404("Favicon topilmadi")


from django.utils import timezone
from main.validators import validate_image_file
from django.core.exceptions import ValidationError
from main.utils import get_client_ip, log_action
from main.models import SiteSetting

@login_required
def onboarding_view(request):
    user = request.user

    # If admin or staff, go to dashboard
    if user.is_superuser or user.is_staff or (hasattr(user, 'role') and user.role in ('admin', 'reception')):
        return redirect('admin_dashboard')

    # If already completed onboarding, redirect to role home
    if getattr(user, 'is_profile_completed', False) and getattr(user, 'terms_accepted', False):
        if user.role == 'teacher':
            return redirect('teacher_home')
        return redirect('student_home')

    site_setting = SiteSetting.objects.first()
    site_name = site_setting.site_name if site_setting and site_setting.site_name else "VLE Ta'lim Tizimi"

    if request.method == 'POST':
        terms_consent = request.POST.get('terms_accepted') == 'on'
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        profile_image = request.FILES.get('profile_image')

        # 1. Terms verification
        if not terms_consent:
            messages.error(request, "Shaxsiy ma'lumotlarni qayta ishlash Nizomi (Ommaviy oferta) shartlariga rozilik bildirishingiz shart.")
            return render(request, 'onboarding.html', {'site_name': site_name, 'user': user})

        # 2. Name validation
        if not first_name or not last_name:
            messages.error(request, "Ism va familiyangizni to'liq kiritishingiz shart.")
            return render(request, 'onboarding.html', {'site_name': site_name, 'user': user})

        # 3. Profile Image validation if provided
        if profile_image:
            try:
                validate_image_file(profile_image)
            except ValidationError as ve:
                messages.error(request, ve.message)
                return render(request, 'onboarding.html', {'site_name': site_name, 'user': user})

        # 4. Optional password change validation
        if new_password or confirm_password:
            if len(new_password) < 6:
                messages.error(request, "Yangi parol kamida 6 ta belgidan iborat bo'lishi kerak.")
                return render(request, 'onboarding.html', {'site_name': site_name, 'user': user})
            if new_password != confirm_password:
                messages.error(request, "Kiritilgan yangi parollar bir-biriga mos kelmadi.")
                return render(request, 'onboarding.html', {'site_name': site_name, 'user': user})
            user.set_password(new_password)
            update_session_auth_hash(request, user)

        # 5. Save user profile data
        user.first_name = first_name
        user.last_name = last_name
        if profile_image:
            user.profile_image = profile_image
        
        client_ip = get_client_ip(request)
        user.terms_accepted = True
        user.terms_accepted_at = timezone.now()
        user.terms_accepted_ip = client_ip
        user.is_profile_completed = True
        user.save()

        log_action(
            user,
            "Onboarding Yakunlandi",
            f"Foydalanuvchi ({user.username}) profilini to'ldirdi va shaxsiy ma'lumotlar nizomiga rozilik bildirdi (IP: {client_ip})",
            request
        )

        messages.success(request, f"Xush kelibsiz, {first_name}! Profilingiz muvaffaqiyatli to'ldirildi.")
        
        if user.role == 'teacher':
            return redirect('teacher_home')
        return redirect('student_home')

    return render(request, 'onboarding.html', {
        'site_name': site_name,
        'user': user
    })




