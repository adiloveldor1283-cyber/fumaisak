import base64
import os
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from main.models import PaymentOrder, StudentPayment, WalletTransaction, CustomUser
from main.utils import run_async, log_action
import logging

logger = logging.getLogger(__name__)

def generate_payme_link(order: PaymentOrder) -> str:
    """
    Payme orqali to'lov havolasini generatsiya qiladi.
    Format: https://checkout.paycom.uz/{base64(m=MERCHANT_ID;ac.order_id=ORDER_ID;a=AMOUNT_IN_TIYIN)}
    """
    merchant_id = getattr(settings, 'PAYME_MERCHANT_ID', '') or os.environ.get('PAYME_MERCHANT_ID', '')
    test_mode = getattr(settings, 'PAYME_TEST_MODE', True)
    
    # Agar Merchant ID sozlanmagan bo'lsa yoki test rejimda bo'lsa
    if not merchant_id or test_mode:
        return f"/student/payment/simulate/{order.id}/"
        
    amount_in_tiyin = int(order.amount * 100)
    params = f"m={merchant_id};ac.order_id={order.id};a={amount_in_tiyin}"
    encoded_params = base64.b64encode(params.encode('utf-8')).decode('utf-8')
    
    base_url = "https://test.paycom.uz" if test_mode else "https://checkout.paycom.uz"
    return f"{base_url}/{encoded_params}"


def generate_click_link(order: PaymentOrder) -> str:
    """
    Click orqali to'lov havolasini generatsiya qiladi.
    Format: https://my.click.uz/services/pay?service_id=...&merchant_id=...&amount=...&transaction_param=...
    """
    service_id = getattr(settings, 'CLICK_SERVICE_ID', '') or os.environ.get('CLICK_SERVICE_ID', '')
    merchant_id = getattr(settings, 'CLICK_MERCHANT_ID', '') or os.environ.get('CLICK_MERCHANT_ID', '')
    test_mode = getattr(settings, 'CLICK_TEST_MODE', True)

    if not service_id or not merchant_id or test_mode:
        return f"/student/payment/simulate/{order.id}/"

    amount_str = f"{order.amount:.2f}"
    return (
        f"https://my.click.uz/services/pay"
        f"?service_id={service_id}&merchant_id={merchant_id}&amount={amount_str}&transaction_param={order.id}&return_url=/student_payment/"
    )


@transaction.atomic
def complete_payment_order(order: PaymentOrder, provider_transaction_id: str = ""):
    """
    To'lov buyurtmasini xavfsiz (atomik) ravishda muvaffaqiyatli deb qayd etadi.
    - Guruh oylik to'lovi bo'lsa: StudentPayment yaratadi/yangilaydi.
    - Balans to'ldirish bo'lsa: CustomUser.balance ga qo'shadi.
    - WalletTransaction ga yozadi.
    - Telegram bot orqali chek yuboradi.
    """
    if order.status == 'paid':
        return order  # Allaqachon to'langan

    order.status = 'paid'
    order.paid_at = timezone.now()
    if provider_transaction_id:
        order.transaction_id = provider_transaction_id
    order.save()

    student = order.student

    if order.group and order.month:
        # Guruh oylik to'lovi
        existing_payment = StudentPayment.objects.filter(
            student=student,
            group=order.group,
            month=order.month
        ).first()

        if existing_payment:
            existing_payment.amount_paid += order.amount
            existing_payment.save()
        else:
            StudentPayment.objects.create(
                student=student,
                group=order.group,
                month=order.month,
                amount_paid=order.amount
            )

        WalletTransaction.objects.create(
            student=student,
            amount=order.amount,
            transaction_type='payment',
            description=f"Guruh to'lovi: {order.group.name} ({order.month}) - {order.provider.capitalize()}"
        )
        msg_text = (
            f"✅ <b>To'lovingiz muvaffaqiyatli qabul qilindi!</b>\n\n"
            f"👤 O'quvchi: <b>{student.get_full_name()}</b>\n"
            f"📚 Guruh: <b>{order.group.name}</b>\n"
            f"🗓 Oy: <b>{order.month}</b>\n"
            f"💰 Summa: <b>{order.amount:,.0f} so'm</b>\n"
            f"💳 To'lov turi: <b>{order.provider.capitalize()}</b>\n"
            f"🧾 Chek ID: <code>#ORD-{order.id}</code>\n\n"
            f"Rahmat, darslaringizda omad tilaymiz!"
        )
    else:
        # Hamyon balansini to'ldirish
        CustomUser.objects.filter(id=student.id).update(balance=student.balance + order.amount)
        student.refresh_from_db(fields=['balance'])

        WalletTransaction.objects.create(
            student=student,
            amount=order.amount,
            transaction_type='top_up',
            description=f"Hamyon to'ldirildi ({order.provider.capitalize()})"
        )
        msg_text = (
            f"💳 <b>Hamyon balansingiz to'ldirildi!</b>\n\n"
            f"👤 O'quvchi: <b>{student.get_full_name()}</b>\n"
            f"➕ To'ldirilgan summa: <b>{order.amount:,.0f} so'm</b>\n"
            f"💼 Yangi balans: <b>{student.balance:,.0f} so'm</b>\n"
            f"💳 To'lov turi: <b>{order.provider.capitalize()}</b>\n"
            f"🧾 Tranzaksiya ID: <code>#ORD-{order.id}</code>"
        )

    # Telegram xabarnoma jo'natish
    if student.telegram_chat_id:
        from main.telegram_service import send_telegram_message
        run_async(send_telegram_message, student.telegram_chat_id, msg_text)

    return order