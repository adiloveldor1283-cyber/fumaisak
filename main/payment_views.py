import json
import base64
import hashlib
import time
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from main.decorators import role_required
from main.models import PaymentOrder, PaymeTransaction, ClickTransaction, Group, StudentPayment
from main.payment_service import generate_payme_link, generate_click_link, complete_payment_order
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# 📱 1. O'QUVCHI UCHUN TO'LOV BUYURTMASI YARATISH (AJAX / POST)
# ==============================================================================
@login_required
@role_required(['student'])
def create_payment_order_view(request):
    if not getattr(settings, 'ONLINE_PAYMENTS_ENABLED', False):
        return JsonResponse({
            'status': 'error',
            'message': "Payme va Click orqali onlayn to'lov tizimi to'liq shakllanmadi. Barcha o'quv to'lovlari o'quv markazi ma'muriyati (retseptsiya) orqali naqd yoki terminal shaklida qabul qilinadi."
        }, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)

    try:
        provider = request.POST.get('provider', '').lower()
        if provider not in ('payme', 'click'):
            return JsonResponse({'status': 'error', 'message': "Noto'g'ri to'lov tizimi tanlandi."}, status=400)

        amount_str = request.POST.get('amount', '').replace(' ', '').replace(',', '')
        amount = Decimal(amount_str)
        if amount < 1000:
            return JsonResponse({'status': 'error', 'message': "Minimal to'lov summasi: 1,000 so'm."}, status=400)

        group_id = request.POST.get('group_id')
        month = request.POST.get('month', '').strip()

        group = None
        if group_id:
            group = Group.objects.filter(id=group_id, students=request.user).first()

        order = PaymentOrder.objects.create(
            student=request.user,
            group=group,
            month=month if group and month else None,
            amount=amount,
            provider=provider,
            status='waiting'
        )

        if provider == 'payme':
            payment_url = generate_payme_link(order)
        else:
            payment_url = generate_click_link(order)

        return JsonResponse({
            'status': 'success',
            'order_id': order.id,
            'payment_url': payment_url
        })

    except Exception as e:
        logger.error(f"Error creating payment order: {e}")
        return JsonResponse({'status': 'error', 'message': f"Xatolik: {str(e)}"}, status=500)


# ==============================================================================
# 💳 2. PAYME JSON-RPC 2.0 WEBHOOK (MERCHANT API)
# ==============================================================================
@csrf_exempt
def payme_webhook_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': {'code': -32600, 'message': 'Invalid Request'}}, status=400)

    # Basic Auth tekshiruvi
    auth_header = request.headers.get('Authorization', '')
    expected_secret = getattr(settings, 'PAYME_SECRET_KEY', '')
    
    if expected_secret:
        if not auth_header.startswith('Basic '):
            return JsonResponse({'error': {'code': -32504, 'message': 'Insufficient privilege'}}, status=401)
        try:
            encoded_credentials = auth_header.split(' ')[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, secret_key = decoded_credentials.split(':', 1)
            if secret_key != expected_secret:
                return JsonResponse({'error': {'code': -32504, 'message': 'Insufficient privilege'}}, status=401)
        except Exception:
            return JsonResponse({'error': {'code': -32504, 'message': 'Invalid authorization header'}}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': {'code': -32700, 'message': 'Parse error'}}, status=400)

    method = data.get('method')
    params = data.get('params', {})
    req_id = data.get('id')

    # 1. CheckPerformTransaction
    if method == 'CheckPerformTransaction':
        account = params.get('account', {})
        order_id = account.get('order_id')
        amount = params.get('amount')

        order = PaymentOrder.objects.filter(id=order_id).first()
        if not order:
            return JsonResponse({'error': {'code': -31050, 'message': {'uz': "Buyurtma topilmadi"}}, 'id': req_id})

        if int(order.amount * 100) != amount:
            return JsonResponse({'error': {'code': -31001, 'message': {'uz': "Noto'g'ri summa"}}, 'id': req_id})

        if order.status == 'paid':
            return JsonResponse({'error': {'code': -31051, 'message': {'uz': "Buyurtma allaqachon to'langan"}}, 'id': req_id})

        return JsonResponse({
            'result': {'allow': True},
            'id': req_id
        })

    # 2. CreateTransaction
    elif method == 'CreateTransaction':
        trans_id = params.get('id')
        trans_time = params.get('time')
        amount = params.get('amount')
        account = params.get('account', {})
        order_id = account.get('order_id')

        order = PaymentOrder.objects.filter(id=order_id).first()
        if not order:
            return JsonResponse({'error': {'code': -31050, 'message': {'uz': "Buyurtma topilmadi"}}, 'id': req_id})

        if int(order.amount * 100) != amount:
            return JsonResponse({'error': {'code': -31001, 'message': {'uz': "Noto'g'ri summa"}}, 'id': req_id})

        trans = PaymeTransaction.objects.filter(transaction_id=trans_id).first()
        if not trans:
            if order.status == 'paid':
                return JsonResponse({'error': {'code': -31051, 'message': {'uz': "Buyurtma allaqachon to'langan"}}, 'id': req_id})

            trans = PaymeTransaction.objects.create(
                order=order,
                transaction_id=trans_id,
                time=trans_time,
                amount=amount,
                state=PaymeTransaction.STATE_CREATED
            )

        return JsonResponse({
            'result': {
                'create_time': int(trans.created_at.timestamp() * 1000),
                'transaction': str(trans.id),
                'state': trans.state
            },
            'id': req_id
        })

    # 3. PerformTransaction
    elif method == 'PerformTransaction':
        trans_id = params.get('id')
        trans = PaymeTransaction.objects.filter(transaction_id=trans_id).first()
        if not trans:
            return JsonResponse({'error': {'code': -31003, 'message': {'uz': "Tranzaksiya topilmadi"}}, 'id': req_id})

        if trans.state == PaymeTransaction.STATE_CREATED:
            trans.state = PaymeTransaction.STATE_COMPLETED
            trans.performed_at = timezone.now()
            trans.save()
            complete_payment_order(trans.order, trans_id)

        return JsonResponse({
            'result': {
                'transaction': str(trans.id),
                'perform_time': int(trans.performed_at.timestamp() * 1000) if trans.performed_at else int(time.time() * 1000),
                'state': trans.state
            },
            'id': req_id
        })

    # 4. CancelTransaction
    elif method == 'CancelTransaction':
        trans_id = params.get('id')
        reason = params.get('reason')
        trans = PaymeTransaction.objects.filter(transaction_id=trans_id).first()
        if not trans:
            return JsonResponse({'error': {'code': -31003, 'message': {'uz': "Tranzaksiya topilmadi"}}, 'id': req_id})

        if trans.state == PaymeTransaction.STATE_CREATED:
            trans.state = PaymeTransaction.STATE_CANCELLED
        elif trans.state == PaymeTransaction.STATE_COMPLETED:
            trans.state = PaymeTransaction.STATE_CANCELLED_AFTER_COMPLETE
        
        trans.reason = reason
        trans.cancelled_at = timezone.now()
        trans.save()

        trans.order.status = 'cancelled'
        trans.order.save()

        return JsonResponse({
            'result': {
                'transaction': str(trans.id),
                'cancel_time': int(trans.cancelled_at.timestamp() * 1000),
                'state': trans.state
            },
            'id': req_id
        })

    # 5. CheckTransaction
    elif method == 'CheckTransaction':
        trans_id = params.get('id')
        trans = PaymeTransaction.objects.filter(transaction_id=trans_id).first()
        if not trans:
            return JsonResponse({'error': {'code': -31003, 'message': {'uz': "Tranzaksiya topilmadi"}}, 'id': req_id})

        return JsonResponse({
            'result': {
                'create_time': int(trans.created_at.timestamp() * 1000),
                'perform_time': int(trans.performed_at.timestamp() * 1000) if trans.performed_at else 0,
                'cancel_time': int(trans.cancelled_at.timestamp() * 1000) if trans.cancelled_at else 0,
                'transaction': str(trans.id),
                'state': trans.state,
                'reason': trans.reason
            },
            'id': req_id
        })

    return JsonResponse({'error': {'code': -32601, 'message': 'Method not found'}}, status=400)


# ==============================================================================
# 🎯 3. CLICK PREPARE & COMPLETE WEBHOOK
# ==============================================================================
@csrf_exempt
def click_webhook_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': -8, 'error_note': 'Error in request method'})

    click_trans_id = request.POST.get('click_trans_id')
    service_id = request.POST.get('service_id')
    click_paydoc_id = request.POST.get('click_paydoc_id')
    merchant_trans_id = request.POST.get('merchant_trans_id')
    amount = request.POST.get('amount')
    action = request.POST.get('action')
    error = request.POST.get('error')
    error_note = request.POST.get('error_note')
    sign_time = request.POST.get('sign_time')
    sign_string = request.POST.get('sign_string')

    secret_key = getattr(settings, 'CLICK_SECRET_KEY', '')

    # Sign hash tekshiruvi (MD5)
    if secret_key:
        expected_sign = hashlib.md5(
            f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}".encode('utf-8')
        ).hexdigest()

        if sign_string != expected_sign:
            return JsonResponse({
                'error': -1,
                'error_note': 'SIGN CHECK FAILED!'
            })

    order = PaymentOrder.objects.filter(id=merchant_trans_id).first()
    if not order:
        return JsonResponse({
            'error': -5,
            'error_note': 'User does not exist'
        })

    if float(order.amount) != float(amount):
        return JsonResponse({
            'error': -2,
            'error_note': 'Incorrect parameter amount'
        })

    # Prepare (action=0)
    if str(action) == '0':
        if order.status == 'paid':
            return JsonResponse({
                'error': -4,
                'error_note': 'Already paid'
            })

        ClickTransaction.objects.update_or_create(
            click_trans_id=click_trans_id,
            defaults={
                'order': order,
                'service_id': service_id,
                'click_paydoc_id': click_paydoc_id,
                'merchant_trans_id': merchant_trans_id,
                'amount': Decimal(amount),
                'action': 0,
                'error': int(error or 0),
                'status': 'waiting'
            }
        )

        return JsonResponse({
            'click_trans_id': click_trans_id,
            'merchant_trans_id': merchant_trans_id,
            'merchant_prepare_id': order.id,
            'error': 0,
            'error_note': 'Success'
        })

    # Complete (action=1)
    elif str(action) == '1':
        if int(error or 0) < 0:
            order.status = 'failed'
            order.save()
            return JsonResponse({
                'error': error,
                'error_note': error_note
            })

        ClickTransaction.objects.update_or_create(
            click_trans_id=click_trans_id,
            defaults={
                'order': order,
                'service_id': service_id,
                'click_paydoc_id': click_paydoc_id,
                'merchant_trans_id': merchant_trans_id,
                'amount': Decimal(amount),
                'action': 1,
                'error': 0,
                'status': 'paid'
            }
        )

        complete_payment_order(order, click_trans_id)

        return JsonResponse({
            'click_trans_id': click_trans_id,
            'merchant_trans_id': merchant_trans_id,
            'merchant_confirm_id': order.id,
            'error': 0,
            'error_note': 'Success'
        })

    return JsonResponse({'error': -3, 'error_note': 'Action not found'})


# ==============================================================================
# 🧪 4. TEST MUHITI (SANDBOX EMULYATORI)
# ==============================================================================
@login_required
def payment_simulation_view(request, order_id):
    order = get_object_or_404(PaymentOrder, id=order_id, student=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm':
            fake_trans_id = f"TEST_{order.provider.upper()}_{uuid.uuid4().hex[:12]}"
            complete_payment_order(order, fake_trans_id)
            messages.success(request, f"{order.amount:,.0f} so'm to'lov muvaffaqiyatli amalga oshirildi (Test Sandbox)!")
            return redirect('student_payment_view')
        elif action == 'cancel':
            order.status = 'cancelled'
            order.save()
            messages.info(request, "To'lov bekor qilindi.")
            return redirect('student_payment_view')

    return render(request, 'payment_sandbox.html', {
        'order': order
    })
import uuid
