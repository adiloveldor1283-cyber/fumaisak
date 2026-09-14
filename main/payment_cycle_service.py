import urllib.parse
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db.models import Sum, Q
from main.models import Group, CustomUser, GroupPaymentInfo, StudentPayment, GroupStudentMembership

MONTH_NAMES = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"
]

def get_student_start_date(student, group):
    """
    O'quvchining guruhdagi to'lov hisobi boshlanish sanasini qaytaradi.
    - Agar o'quvchi guruh ochilganda bo'lsa -> Guruh to'lov boshlanish sanasi.
    - Agar keyinroq qo'shilgan bo'lsa -> O'zi guruhga qo'shilgan sana (joined_at).
    """
    payment_info = getattr(group, 'payment_info', None)
    if payment_info:
        group_start = payment_info.get_start_date()
    elif group.created_at:
        group_start = group.created_at.date()
    else:
        group_start = timezone.now().date()

    membership = GroupStudentMembership.objects.filter(student=student, group=group).first()
    if membership and membership.joined_at:
        joined_date = timezone.localtime(membership.joined_at).date()
        if joined_date > group_start:
            return joined_date
    return group_start


def get_student_payment_cycles(student, group):
    """
    O'quvchining guruh bo'yicha barcha to'lov davrlarini (1-oy, 2-oy...) va ularning to'lov holatini hisoblab qaytaradi.
    """
    payment_info = getattr(group, 'payment_info', None)
    if not payment_info or payment_info.monthly_fee <= 0:
        return []

    duration_months = payment_info.course_duration_months or 6
    monthly_fee = float(payment_info.monthly_fee)
    start_date = get_student_start_date(student, group)
    today = timezone.now().date()

    # O'quvchining ushbu guruhdagi barcha to'lovlarini olamiz
    existing_payments = list(StudentPayment.objects.filter(student=student, group=group).order_by('paid_at'))

    cycles = []
    
    # Har bir davrni tekshiramiz
    for i in range(1, duration_months + 1):
        c_start = start_date + relativedelta(months=i-1)
        c_end = start_date + relativedelta(months=i)
        
        start_str = c_start.strftime('%d.%m.%Y')
        end_str = c_end.strftime('%d.%m.%Y')
        label = f"{i}-oy ({start_str} — {end_str})"
        month_name = MONTH_NAMES[c_start.month - 1]

        # Ushbu davrga tegishli to'lovlarni topamiz
        cycle_payments = []
        for p in existing_payments:
            # 1. Aniq cycle_number yoki period_start mos kelsa
            if p.cycle_number == i:
                cycle_payments.append(p)
            elif p.period_start == c_start and p.period_end == c_end:
                cycle_payments.append(p)
            elif p.month == label:
                cycle_payments.append(p)
            elif not p.cycle_number and not p.period_start:
                # Legacy to'lovlar: oy nomi yoki oddiy matn bo'yicha moslash
                if p.month == month_name or p.month.startswith(f"{i}-oy") or p.month.startswith(month_name):
                    cycle_payments.append(p)

        total_paid = sum(float(p.amount_paid) for p in cycle_payments)
        remaining_debt = max(0.0, monthly_fee - total_paid)

        is_due = today >= c_start
        is_current = c_start <= today < c_end

        if total_paid >= monthly_fee:
            status = 'paid'
            status_label = "To'langan"
            status_color = '#00ffaa'
        elif total_paid > 0:
            status = 'partial'
            status_label = f"Qisman ({int(total_paid):,} so'm to'langan)"
            status_color = '#ff9f43'
        elif is_due:
            status = 'unpaid'
            status_label = "To'lanmagan (Qarzdor)"
            status_color = '#ff4a5a'
        else:
            status = 'future'
            status_label = "Kutilmoqda"
            status_color = 'rgba(255,255,255,0.4)'

        cycles.append({
            'cycle_number': i,
            'start_date': c_start.isoformat(),
            'end_date': c_end.isoformat(),
            'start_date_str': start_str,
            'end_date_str': end_str,
            'label': label,
            'month_name': month_name,
            'monthly_fee': monthly_fee,
            'total_paid': total_paid,
            'remaining_debt': remaining_debt,
            'status': status,
            'status_label': status_label,
            'status_color': status_color,
            'is_due': is_due,
            'is_current': is_current,
            'payment_count': len(cycle_payments),
        })

    return cycles


def get_next_payable_cycle(student, group):
    """
    O'quvchi uchun to'lash kerak bo'lgan navbatdagi davrni qaytaradi.
    """
    cycles = get_student_payment_cycles(student, group)
    for c in cycles:
        if c['status'] != 'paid':
            return c
    return cycles[-1] if cycles else None


def get_all_group_debtors(group_id=None):
    """
    Guruhlar yoki tanlangan guruh bo'yicha to'lov muddati yetib kelgan va qarzi bor barcha o'quvchilarni qaytaradi.
    """
    groups_qs = Group.objects.select_related('payment_info').prefetch_related('students').all()
    if group_id and group_id != 'all':
        groups_qs = groups_qs.filter(id=group_id)

    debtors = []
    today = timezone.now().date()

    for group in groups_qs:
        payment_info = getattr(group, 'payment_info', None)
        if not payment_info or payment_info.monthly_fee <= 0:
            continue

        monthly_fee = float(payment_info.monthly_fee)
        students = group.students.all()

        for student in students:
            cycles = get_student_payment_cycles(student, group)
            # Muddati kelgan (is_due) va qarz qolgan davrlarni olamiz
            due_unpaid_cycles = [c for c in cycles if c['is_due'] and c['remaining_debt'] > 0]
            
            if due_unpaid_cycles:
                total_debt = sum(c['remaining_debt'] for c in due_unpaid_cycles)
                total_paid_due = sum(c['total_paid'] for c in due_unpaid_cycles)
                
                # Eng birinchi to'lanmagan davr
                first_unpaid = due_unpaid_cycles[0]
                
                if len(due_unpaid_cycles) == 1:
                    period_description = first_unpaid['label']
                else:
                    period_description = f"{len(due_unpaid_cycles)} ta davr ({first_unpaid['start_date_str']} — {due_unpaid_cycles[-1]['end_date_str']})"

                student_name = f"{student.first_name} {student.last_name}".strip() or student.username
                
                msg = f"Salom! Hurmatli {student_name}, {group.name} guruhi uchun {period_description} to'lovidan {int(total_debt):,} so'm qarzdorligingiz mavjud. Iltimos, to'lovni tez orada amalga oshiring. Rahmat!"
                tg_share_url = f"https://t.me/share/url?text={urllib.parse.quote(msg)}"

                debtors.append({
                    'student': student,
                    'student_name': student_name,
                    'group': group,
                    'monthly_fee': monthly_fee,
                    'total_paid': total_paid_due,
                    'debt_amount': total_debt,
                    'period_label': period_description,
                    'unpaid_cycles': due_unpaid_cycles,
                    'telegram_url': tg_share_url,
                    'raw_message': msg,
                })

    debtors.sort(key=lambda x: x['debt_amount'], reverse=True)
    return debtors
