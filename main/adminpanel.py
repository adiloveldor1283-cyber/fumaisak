from main.sms_service import clean_phone_number, generate_otp_code, send_sms, get_eskiz_settings, generate_random_password, get_eskiz_balance
import csv
import io
import os
from collections import defaultdict
from itertools import groupby
from operator import attrgetter

from django.contrib.auth.hashers import make_password
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.utils.timezone import make_aware
from reportlab.pdfgen import canvas as pdf_canvas

from main.models import Group, CustomUser, Schedule, DAYS_OF_WEEK, Assignment, Question, Quiz, Answer, \
    GroupStudentMembership, GroupPaymentInfo, StudentPayment, SiteSetting, Attendance, GroupVideo, StudentQuizResult, AssignmentSubmission, \
    ProfileSetting, UserSession, AuditLog, Subject, SubjectMaterial, Book, GroupLesson, WalletTransaction, TeacherSalaryPayment
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime, timedelta
import urllib.parse
from django.utils.dateparse import parse_time
from django.http import HttpResponseForbidden
from django.utils.dateparse import parse_datetime
from django.utils.html import escape
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle



from django.db.models import Sum, Q, Count, F
from django.db import transaction
from django.views.decorators.http import require_POST
from main.utils import log_action
from main.decorators import admin_required, role_required, subadmin_permission_required

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_ITALIC = 'Helvetica-Oblique'

try:
    font_path = r"C:\Windows\Fonts\arial.ttf"
    font_bold_path = r"C:\Windows\Fonts\arialbd.ttf"
    font_italic_path = r"C:\Windows\Fonts\ariali.ttf"
    
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('Arial', font_path))
        FONT_NAME = 'Arial'
        
    if os.path.exists(font_bold_path):
        pdfmetrics.registerFont(TTFont('Arial-Bold', font_bold_path))
        FONT_BOLD = 'Arial-Bold'
        
    if os.path.exists(font_italic_path):
        pdfmetrics.registerFont(TTFont('Arial-Italic', font_italic_path))
        FONT_ITALIC = 'Arial-Italic'
except Exception as e:
    pass

@role_required(['admin', 'reception'])
def admin_dashboard(request):
    total_students = CustomUser.objects.filter(role='student').count()
    total_teachers = CustomUser.objects.filter(role='teacher').count()
    total_groups = Group.objects.count()
    
    total_payments = StudentPayment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0

    recent_payments = StudentPayment.objects.select_related('student', 'group').order_by('-paid_at')[:5]
    recent_students = CustomUser.objects.filter(role='student').order_by('-joined_at')[:5]
    recent_assignments = Assignment.objects.select_related('group').order_by('-created_at')[:5]

    active_sessions_count = UserSession.objects.filter(is_active=True).count()

    # Dynamic Analytics Calculations for Chart.js Graphs
    import datetime
    import json
    from django.db.models import Count, Q
    from django.db.models.functions import TruncMonth

    # 1. Income trend (last 6 months)
    income_data = StudentPayment.objects.annotate(month_date=TruncMonth('paid_at'))\
        .values('month_date')\
        .annotate(total=Sum('amount_paid'))\
        .order_by('-month_date')[:6]
    
    income_months = []
    income_totals = []
    for item in reversed(income_data):
        if item['month_date']:
            income_months.append(item['month_date'].strftime('%b %Y'))
            income_totals.append(float(item['total']))
            
    # 2. Subject Popularity (students count per subject)
    subject_popularity = Subject.objects.annotate(
        student_count=Count('groups__students', distinct=True)
    ).values('name', 'student_count').order_by('-student_count')[:5]
    
    subj_names = [item['name'] for item in subject_popularity]
    subj_counts = [item['student_count'] for item in subject_popularity]
    
    # 3. Attendance stats (last 7 days / 1 hafta)
    today = timezone.localdate()
    seven_days_ago = today - datetime.timedelta(days=7)
    attendance_stats = Attendance.objects.filter(date__gte=seven_days_ago)\
        .values('status')\
        .annotate(count=Count('id'))
        
    att_present = 0
    att_absent = 0
    for stat in attendance_stats:
        if stat['status'] == 'present':
            att_present = stat['count']
        elif stat['status'] == 'absent':
            att_absent = stat['count']

    # Agar joriy oxirgi 7 kunda hali davomat olinmagan bo'lsa, tizimdagi eng so'nggi 1 haftalik darslar bo'yicha ko'rsatamiz
    if att_present == 0 and att_absent == 0:
        latest_att = Attendance.objects.order_by('-date').first()
        if latest_att:
            fallback_start = latest_att.date - datetime.timedelta(days=7)
            fallback_stats = Attendance.objects.filter(date__gte=fallback_start, date__lte=latest_att.date)\
                .values('status')\
                .annotate(count=Count('id'))
            for stat in fallback_stats:
                if stat['status'] == 'present':
                    att_present = stat['count']
                elif stat['status'] == 'absent':
                    att_absent = stat['count']
            
    # 4. Student growth (last 6 months)
    student_growth = CustomUser.objects.filter(role='student', joined_at__isnull=False)\
        .annotate(month_date=TruncMonth('joined_at'))\
        .values('month_date')\
        .annotate(count=Count('id'))\
        .order_by('-month_date')[:6]
        
    growth_months = []
    growth_counts = []
    for item in reversed(student_growth):
        if item['month_date']:
            growth_months.append(item['month_date'].strftime('%b %Y'))
            growth_counts.append(item['count'])

    return render(request, 'admin_dashboard.html', {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_groups': total_groups,
        'total_payments': total_payments,
        'recent_payments': recent_payments,
        'recent_students': recent_students,
        'recent_assignments': recent_assignments,
        'active_sessions_count': active_sessions_count,
        # Chart JSON data
        'income_months': json.dumps(income_months),
        'income_totals': json.dumps(income_totals),
        'subj_names': json.dumps(subj_names),
        'subj_counts': json.dumps(subj_counts),
        'att_present': att_present,
        'att_absent': att_absent,
        'growth_months': json.dumps(growth_months),
        'growth_counts': json.dumps(growth_counts),
    })

@role_required(['admin', 'reception'])
def admin_warning_students_api(request):
    # Calculate warning students globally for all active students (Admin view)
    from collections import defaultdict
    warning_students = []
    active_students_qs = CustomUser.objects.filter(
        role='student', 
        student_groups__isnull=False
    ).prefetch_related(
        'student_groups__teachers', 
        'student_groups__subject'
    ).distinct()
    
    from django.db.models import Count, Q
    attendance_stats = Attendance.objects.filter(student__in=active_students_qs)\
        .values('student_id', 'group_id')\
        .annotate(
            total_att=Count('id'),
            present_att=Count('id', filter=Q(status='present'))
        )
    att_stats_lookup = {
        (stat['student_id'], stat['group_id']): (stat['total_att'], stat['present_att'])
        for stat in attendance_stats
    }

    all_quiz_results = StudentQuizResult.objects.filter(student__in=active_students_qs).select_related('quiz')
    all_submissions = AssignmentSubmission.objects.filter(student__in=active_students_qs, grade__isnull=False).select_related('assignment')

    quiz_by_student = defaultdict(list)
    for qr in all_quiz_results:
        quiz_by_student[qr.student_id].append(qr)
        
    sub_by_student = defaultdict(list)
    for sub in all_submissions:
        sub_by_student[sub.student_id].append(sub)
        
    for s in active_students_qs:
        s_groups = s.student_groups.all()
        for g in s_groups:
            total_att, present_att = att_stats_lookup.get((s.id, g.id), (0, 0))
            att_rate = (present_att / total_att) if total_att > 0 else 1.0
            
            reasons = []
            if total_att >= 3 and att_rate < 0.70:
                reasons.append(f"Past davomat ({round(att_rate * 100)}%)")
                
            g_quizzes = [r for r in quiz_by_student[s.id] if r.quiz.group_id == g.id]
            g_submissions = [sub for sub in sub_by_student[s.id] if sub.assignment.group_id == g.id]
            
            grades = []
            for r in g_quizzes:
                pct = (r.score / r.quiz.max_score * 100) if r.quiz.max_score > 0 else 0
                grades.append((r.quiz.created_at, pct))
            for sub in g_submissions:
                pct = (sub.grade / sub.assignment.max_score * 100) if sub.assignment.max_score > 0 else 0
                grades.append((sub.assignment.created_at, pct))
                
            grades.sort(key=lambda x: x[0])
            
            if len(grades) >= 3:
                last_3 = [grade_item[1] for grade_item in grades[-3:]]
                if last_3[0] > last_3[1] > last_3[2]:
                    reasons.append(f"O'zlashtirish pasaymoqda (Oxirgi 3 baho: {round(last_3[0])}% -> {round(last_3[1])}% -> {round(last_3[2])}%)")
                    
            if reasons:
                teachers_list = g.teachers.all()
                teachers_str = ", ".join([t.get_full_name() or t.username for t in teachers_list]) if teachers_list else "Noma'lum"
                warning_students.append({
                    'student': s.get_full_name() or s.username,
                    'group': g.name,
                    'subject': g.subject.name if g.subject else "Noma'lum",
                    'teacher': teachers_str,
                    'reasons': reasons
                })

    return JsonResponse({'warning_students': warning_students})

@subadmin_permission_required('manage_payments')
def admin_all_payments(request):
    query = request.GET.get('query', '').strip()
    payments_list = StudentPayment.objects.select_related('student', 'group').order_by('-paid_at')
    
    if query:
        payments_list = payments_list.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(group__name__icontains=query) |
            Q(month__icontains=query)
        )

    from django.core.paginator import Paginator
    paginator = Paginator(payments_list, 50)
    page_number = request.GET.get('page')
    payments = paginator.get_page(page_number)

    return render(request, 'admin_all_payments.html', {
        'payments': payments,
        'query': query
    })

#Guruh uchun
@subadmin_permission_required('manage_groups')
def all_groups_admin(request):
    groups = Group.objects.select_related('subject').all().order_by('-created_at')
    return render(request, 'all_groups_admin.html', {'groups': groups})


@subadmin_permission_required('manage_groups')
@transaction.atomic
def edit_group_admin(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    all_teachers = CustomUser.objects.filter(role='teacher').exclude(teachers_groups=group).prefetch_related('subjects')
    all_students = CustomUser.objects.filter(role='student').exclude(student_groups=group)
    all_subjects = Subject.objects.all().order_by('name')

    if request.method == 'POST':
        if 'delete' in request.POST:
            if request.user.role != 'admin' and not request.user.is_superuser:
                messages.error(request, "Faqat bosh administrator guruhni o'chira oladi!", extra_tags='edit_group')
                return redirect('edit_group_admin', group_id=group.id)
            group_name = group.name
            group_id_val = group.id
            group.delete()
            log_action(request.user, "Guruh O'chirildi", f"Guruh o'chirildi: {group_name} (ID: {group_id_val})", request)
            messages.success(request, "Guruh muvaffaqiyatli o‘chirildi.", extra_tags='edit_group')
            return redirect('all_groups_admin')

        group.name = request.POST.get('group-name')
        
        subject_id = request.POST.get('subject')
        if subject_id:
            group.subject_id = subject_id
        else:
            group.subject = None

        date_str = f"{request.POST.get('date')} {request.POST.get('time')}"  # '2025-06-28 13:15'
        naive_datetime = parse_datetime(date_str)
        aware_datetime = make_aware(naive_datetime) if naive_datetime else timezone.now()

        group.created_at = aware_datetime
        group.save()

        if 'selected_teachers' in request.POST:
            selected_teacher_ids = request.POST.getlist('selected_teachers')
            teachers = CustomUser.objects.filter(id__in=selected_teacher_ids, role='teacher')
            group.teachers.set(teachers)

        if 'selected_students' in request.POST:
            selected_student_ids = request.POST.getlist('selected_students')
            selected_student_ids = list(map(int, selected_student_ids))

            existing_memberships = GroupStudentMembership.objects.filter(group=group)
            existing_student_ids = set(existing_memberships.values_list('student_id', flat=True))
            new_student_ids = set(selected_student_ids)

            students_to_add = new_student_ids - existing_student_ids
            students_to_remove = existing_student_ids - new_student_ids

            memberships_to_create = [
                GroupStudentMembership(group=group, student_id=student_id)
                for student_id in students_to_add
            ]
            GroupStudentMembership.objects.bulk_create(memberships_to_create, ignore_conflicts=True)

            GroupStudentMembership.objects.filter(group=group, student_id__in=students_to_remove).delete()

        log_action(request.user, "Guruh Tahrirlandi", f"Guruh ma'lumotlari tahrirlandi: {group.name} (ID: {group.id})", request)
        messages.success(request, "Guruh muvaffaqiyatli saqlandi.", extra_tags='edit_group')
        return redirect('all_groups_admin')

    context = {
        'group': group,
        'group_teachers': group.teachers.prefetch_related('subjects'),
        'all_teachers': all_teachers,
        'all_students': all_students,
        'all_subjects': all_subjects,
    }
    return render(request, 'edit_group_admin.html', context)

@subadmin_permission_required('manage_groups')
@transaction.atomic
def create_group_admin(request):
    all_teachers = CustomUser.objects.filter(role='teacher').prefetch_related('subjects')
    all_students = CustomUser.objects.filter(role='student')
    all_subjects = Subject.objects.all().order_by('name')

    if request.method == 'POST':
        name = request.POST.get('group-name')
        subject_id = request.POST.get('subject')
        
        datetime_str = f"{request.POST.get('date')} {request.POST.get('time')}"
        naive_dt = parse_datetime(datetime_str)

        # Agar timezone aktiv bo‘lsa va datetime naive bo‘lsa — make_aware qilamiz
        created_at = make_aware(naive_dt) if naive_dt else timezone.now()

        selected_teacher_ids = request.POST.getlist('selected_teachers')
        selected_student_ids = request.POST.getlist('selected_students')

        group = Group.objects.create(name=name, created_at=created_at)
        if subject_id:
            group.subject_id = subject_id
            group.save()
            
        group.teachers.set(CustomUser.objects.filter(id__in=selected_teacher_ids))
        
        memberships_to_create = [
            GroupStudentMembership(group=group, student_id=int(student_id))
            for student_id in selected_student_ids
        ]
        GroupStudentMembership.objects.bulk_create(memberships_to_create, ignore_conflicts=True)

        log_action(request.user, "Guruh Yaratildi", f"Yangi guruh yaratildi: {group.name} (ID: {group.id})", request)

        messages.success(request, "Yangi guruh muvaffaqiyatli yaratildi.", extra_tags='yangi_guruh')
        return redirect('all_groups_admin')


    context = {
        'all_teachers': all_teachers,
        'all_students': all_students,
        'all_subjects': all_subjects,
        'timezone': timezone,
        'date_now': timezone.localtime(timezone.now()).strftime('%d.%m.%Y'),
        'time_now': timezone.localtime(timezone.now()).strftime('%H:%M:%S'),
    }
    return render(request, 'group_create_admin.html', context)

#Sudent uchun
@subadmin_permission_required('manage_students')
def students_list_admin(request):

    if request.method == 'POST':
        if request.user.role != 'admin' and not request.user.is_superuser:
            messages.error(request, "Faqat bosh administrator o'quvchilarni o'chira oladi!", extra_tags='edit_user')
            return redirect('students_list_admin')
        selected_ids = request.POST.getlist('selected_users')
        if selected_ids:
            deleted_count = CustomUser.objects.filter(id__in=selected_ids, role='student').delete()[0]
            log_action(request.user, "Talabalar O'chirildi", f"{deleted_count} ta talaba ro'yxatdan o'chirildi. (IDs: {selected_ids})", request)
            messages.success(request, f"{deleted_count} ta o‘quvchi muvaffaqiyatli o‘chirildi.", extra_tags='edit_user')
        else:
            messages.warning(request, "Hech qanday o‘quvchi tanlanmadi.", extra_tags='edit_user')
        return redirect('students_list_admin')  # nomini urls.py dan tekshiring!

    # GET so‘rov bo‘lsa - ro‘yxatni qaytaradi
    students = CustomUser.objects.filter(role='student')
    total_students = students.count()
    active_students = students.filter(is_active=True).count()
    inactive_students = students.filter(is_active=False).count()
    groups = Group.objects.all()

    return render(request, 'users-list-admin.html', {
        'students': students,
        'total_students': total_students,
        'active_students': active_students,
        'inactive_students': inactive_students,
        'groups': groups,
    })

@subadmin_permission_required('manage_students')
def add_student(request):
    groups = Group.objects.all().order_by('name')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        group_id = request.POST.get('group_id', '').strip()
        role = request.POST.get('role', 'student').strip() or 'student'
        is_active = request.POST.get('is_active') == 'on'
        profile_image = request.FILES.get('profile_image')
        otp_code = request.POST.get('otp_code', '').strip()

        if not phone_number:
            messages.error(request, "Telefon raqami to‘ldirilishi majburiy.", extra_tags='password_creat')
            return redirect('add_student')

        phone_clean = clean_phone_number(phone_number)
        if not phone_clean or len(phone_clean) != 12:
            messages.error(request, "Telefon raqami noto'g'ri formatda. Namuna: +998901234567", extra_tags='password_creat')
            return redirect('add_student')

        # Check phone verification in session or via OTP
        is_verified = request.session.get(f'sms_verified_{phone_clean}', False)
        if not is_verified and otp_code:
            stored_otp_data = request.session.get(f'phone_otp_{phone_clean}')
            if stored_otp_data and isinstance(stored_otp_data, dict):
                if str(stored_otp_data.get('otp')) == str(otp_code):
                    is_verified = True

        # Generate username if empty
        if not username:
            username = f"std_{phone_clean[3:]}"

        # If username exists, resolve conflict
        orig_username = username
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{orig_username}_{counter}"
            counter += 1

        if profile_image:
            from main.validators import validate_image_file
            from django.core.exceptions import ValidationError
            try:
                validate_image_file(profile_image)
            except ValidationError as ve:
                messages.error(request, ve.message, extra_tags='password_creat')
                return redirect('add_student')

        # Auto-generate secure strong password
        raw_password = generate_random_password(8)

        # System creates account with empty names; student fills them during onboarding (O'RQ-547)
        user = CustomUser.objects.create(
            username=username,
            first_name="",
            last_name="",
            phone_number=phone_number,
            password=make_password(raw_password),
            role=role,
            is_active=is_active,
            is_profile_completed=False,
            terms_accepted=False
        )
        if profile_image:
            user.profile_image = profile_image
            user.save()

        # Link student to group if selected
        if group_id:
            try:
                group_obj = Group.objects.get(id=group_id)
                GroupStudentMembership.objects.get_or_create(student=user, group=group_obj)
            except (Group.DoesNotExist, ValueError):
                pass

        # Send credentials via SMS
        site_setting = SiteSetting.objects.first()
        site_name = site_setting.site_name if site_setting and site_setting.site_name else "VLE Tizimi"
        site_url = request.build_absolute_uri('/')
        greeting = f"Assalomu alaykum, {first_name}!" if first_name else "Assalomu alaykum!"
        sms_text = f"{greeting} {site_name} tizimidagi profilingiz yaratildi.\nLogin: {username}\nParol: {raw_password}\nKirish: {site_url}"
        sms_res = send_sms(phone_clean, sms_text, check_enabled=True)

        # Clear OTP from session
        request.session.pop(f'phone_otp_{phone_clean}', None)
        request.session.pop(f'sms_verified_{phone_clean}', None)

        display_name = f"{user.first_name} {user.last_name}".strip() or user.username
        log_action(request.user, "Talaba Qo'shildi", f"Yangi talaba qo'shildi: {user.username} ({display_name})", request)
        
        if sms_res.get('success'):
            messages.success(request, f"O'quvchi muvaffaqiyatli qo'shildi! Login: {username}, Parol: {raw_password} (SMS orqali yuborildi).", extra_tags='edit_user')
        else:
            messages.success(request, f"O'quvchi muvaffaqiyatli qo'shildi! Login: {username}, Parol: {raw_password}.", extra_tags='edit_user')
        return redirect('students_list_admin')

    return render(request, 'add-student.html', {
        'groups': groups
    })


def edit_student(request, student_id):

    student = get_object_or_404(CustomUser, id=student_id)
    if request.method == 'POST':
        username = request.POST.get('username')
        if username:
            student.username = username

        first_name = request.POST.get('first_name')
        if first_name:
            student.first_name = first_name

        last_name = request.POST.get('last_name')
        if last_name:
            student.last_name = last_name

        phone_number = request.POST.get('phone_number')
        if phone_number:
            student.phone_number = phone_number

        is_active_val = request.POST.get('is_active')
        if is_active_val is not None:
            student.is_active = (is_active_val == 'true')

        if 'profile_image' in request.FILES:
            profile_image = request.FILES['profile_image']
            from main.validators import validate_image_file
            from django.core.exceptions import ValidationError
            try:
                validate_image_file(profile_image)
            except ValidationError as ve:
                messages.error(request, ve.message, extra_tags='edit_user')
                return redirect('edit_student', student_id=student.id)
            student.profile_image = profile_image

        student.save()
        log_action(request.user, "Talaba Tahrirlandi", f"Talaba ma'lumotlari tahrirlandi: {student.username} ({student.first_name} {student.last_name})", request)
        messages.success(request, "O'quvchi ma'lumotlari saqlandi.", extra_tags='edit_user')
        return redirect('students_list_admin')

    return render(request, 'student-tahrirlash.html', {'student': student})

#O'qituvchilar uchun
@subadmin_permission_required('manage_teachers')
def teachers_list_admin(request):

    if request.method == 'POST':
        if request.user.role != 'admin' and not request.user.is_superuser:
            messages.error(request, "Faqat bosh administrator o'qituvchilarni o'chira oladi!", extra_tags='teacher_list')
            return redirect('teachers_list_admin')
        selected_ids = request.POST.getlist('selected_users')
        if selected_ids:
            deleted_count = CustomUser.objects.filter(id__in=selected_ids, role='teacher').delete()[0]
            log_action(request.user, "O'qituvchilar O'chirildi", f"{deleted_count} ta o'qituvchi o'chirildi. (IDs: {selected_ids})", request)
            messages.success(request, f"{deleted_count} ta o‘qituvchi muvaffaqiyatli o‘chirildi.", extra_tags='teacher_list')
        else:
            messages.warning(request, "Hech qanday o‘qituvchi tanlanmadi.", extra_tags='teacher_list')
        return redirect('teachers_list_admin')

    # GET so‘rov bo‘lsa - ro‘yxatni qaytaradi
    teachers = CustomUser.objects.filter(role='teacher').prefetch_related('subjects', 'teachers_groups')
    total_teachers = teachers.count()
    active_teachers = teachers.filter(is_active=True).count()
    inactive_teachers = teachers.filter(is_active=False).count()
    subjects = Subject.objects.all().order_by('name')

    return render(request, 'teachers-list-admin.html', {
        'teachers': teachers,
        'total_teachers': total_teachers,
        'active_teachers': active_teachers,
        'inactive_teachers': inactive_teachers,
        'subjects': subjects,
    })

@subadmin_permission_required('manage_teachers')
def edit_teacher(request, teacher_id):

    teacher = get_object_or_404(CustomUser, id=teacher_id)
    all_subjects = Subject.objects.all().order_by('name')

    if request.method == 'POST':
        username = request.POST.get('teacher_username')
        if username:
            teacher.username = username

        first_name = request.POST.get('first_name')
        if first_name:
            teacher.first_name = first_name

        last_name = request.POST.get('last_name')
        if last_name:
            teacher.last_name = last_name

        phone_number = request.POST.get('phone_number')
        if phone_number:
            teacher.phone_number = phone_number

        is_active_val = request.POST.get('is_active')
        if is_active_val is not None:
            teacher.is_active = (is_active_val == 'true')

        if 'profile_image' in request.FILES:
            profile_image = request.FILES['profile_image']
            from main.validators import validate_image_file
            from django.core.exceptions import ValidationError
            try:
                validate_image_file(profile_image)
            except ValidationError as ve:
                messages.error(request, ve.message, extra_tags='teacher_list')
                return redirect('edit_teacher', teacher_id=teacher.id)
            teacher.profile_image = profile_image

        teacher.save()
        
        # Save subjects M2M
        selected_subjects = request.POST.getlist('subjects')
        teacher.subjects.set(selected_subjects)

        log_action(request.user, "O'qituvchi Tahrirlandi", f"O'qituvchi ma'lumotlari tahrirlandi: {teacher.username} ({teacher.first_name} {teacher.last_name})", request)
        messages.success(request, "O'qituvchi ma'lumotlari saqlandi.", extra_tags='teacher_list')
        return redirect('teachers_list_admin')

    return render(request, 'teacher-tahrirlash.html', {
        'teacher': teacher,
        'all_subjects': all_subjects
    })

@subadmin_permission_required('manage_teachers')
def add_teacher(request):

    all_subjects = Subject.objects.all().order_by('name')

    if request.method == 'POST':
        username = request.POST.get('teacher_username', '').strip()
        first_name = request.POST.get('teacher_first_name', '').strip()
        last_name = request.POST.get('teacher_last_name', '').strip()
        phone_number = request.POST.get('teacher_phone_number', '').strip()
        role = request.POST.get('role', 'teacher').strip() or 'teacher'
        is_active = request.POST.get('is_active') == 'on'
        profile_image = request.FILES.get('profile_image')
        otp_code = request.POST.get('otp_code', '').strip()

        if not phone_number:
            messages.error(request, "Telefon raqami to‘ldirilishi majburiy.", extra_tags='password_creat_teacher')
            return redirect('add_teacher')

        phone_clean = clean_phone_number(phone_number)
        if not phone_clean or len(phone_clean) != 12:
            messages.error(request, "Telefon raqami noto'g'ri formatda. Namuna: +998901234567", extra_tags='password_creat_teacher')
            return redirect('add_teacher')

        # Check phone verification in session or via OTP
        is_verified = request.session.get(f'sms_verified_{phone_clean}', False)
        if not is_verified and otp_code:
            stored_otp_data = request.session.get(f'phone_otp_{phone_clean}')
            if stored_otp_data and isinstance(stored_otp_data, dict):
                if str(stored_otp_data.get('otp')) == str(otp_code):
                    is_verified = True

        # Generate username if empty
        if not username:
            username = f"t_{phone_clean[3:]}"

        # If username exists, resolve conflict
        orig_username = username
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{orig_username}_{counter}"
            counter += 1

        if profile_image:
            from main.validators import validate_image_file
            from django.core.exceptions import ValidationError
            try:
                validate_image_file(profile_image)
            except ValidationError as ve:
                messages.error(request, ve.message, extra_tags='password_creat_teacher')
                return redirect('add_teacher')

        # Auto-generate secure strong password
        raw_password = generate_random_password(8)

        # System creates teacher account with empty names; teacher fills them during onboarding (O'RQ-547)
        new_teacher = CustomUser.objects.create(
            username=username,
            first_name="",
            last_name="",
            phone_number=phone_number,
            password=make_password(raw_password),
            role=role,
            is_active=is_active,
            profile_image=profile_image,
            is_profile_completed=False,
            terms_accepted=False
        )
        
        # Save subjects M2M
        selected_subjects = request.POST.getlist('subjects')
        if selected_subjects:
            new_teacher.subjects.set(selected_subjects)

        # Send credentials via SMS
        site_setting = SiteSetting.objects.first()
        site_name = site_setting.site_name if site_setting and site_setting.site_name else "VLE Tizimi"
        site_url = request.build_absolute_uri('/')
        greeting = f"Assalomu alaykum, {first_name}!" if first_name else "Assalomu alaykum!"
        sms_text = f"{greeting} {site_name} tizimidagi o'qituvchi profilingiz yaratildi.\nLogin: {username}\nParol: {raw_password}\nKirish: {site_url}"
        sms_res = send_sms(phone_clean, sms_text, check_enabled=True)

        # Clear OTP from session
        request.session.pop(f'phone_otp_{phone_clean}', None)
        request.session.pop(f'sms_verified_{phone_clean}', None)

        display_name = f"{new_teacher.first_name} {new_teacher.last_name}".strip() or new_teacher.username
        log_action(request.user, "O'qituvchi Qo'shildi", f"Yangi o'qituvchi qo'shildi: {new_teacher.username} ({display_name})", request)
        
        if sms_res.get('success'):
            messages.success(request, f"O'qituvchi muvaffaqiyatli qo‘shildi! Login: {username}, Parol: {raw_password} (SMS orqali yuborildi).", extra_tags='teacher_list')
        else:
            messages.success(request, f"O'qituvchi muvaffaqiyatli qo‘shildi! Login: {username}, Parol: {raw_password}.", extra_tags='teacher_list')
        return redirect('teachers_list_admin')

    return render(request, 'add-teacher.html', {'all_subjects': all_subjects})


def admin_password(request):
    user = request.user
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        if not user.check_password(old_password):
            messages.error(request, "Eski parol noto‘g‘ri!", extra_tags='admin_password')
        elif new_password1 != new_password2:
            messages.error(request, "Yangi parollar bir xil emas!", extra_tags='admin_password')
        elif len(new_password1) < 8:
            messages.error(request, "Yangi parol kamida 8 ta belgidan iborat bo‘lishi kerak!", extra_tags='admin_password')
        else:
            user.set_password(new_password1)
            user.save()
            logout(request)
            messages.success(request, "Parolingiz o‘zgartirildi. Qaytadan tizimga kiring.", extra_tags='admin_password_login')
            return redirect('login')  # yoki boshqa sahifa

    return render(request, 'admin_password.html')

@admin_required
def reset_student_password(request, student_id):

    student = get_object_or_404(CustomUser, id=student_id, role='student')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if not password1 or not password2:
            messages.error(request, "Iltimos, barcha maydonlarni to‘ldiring.", extra_tags='reset_password')
        elif password1 != password2:
            messages.error(request, "Parollar mos kelmayapti.", extra_tags='reset_password')
        elif len(password1) < 8:
            messages.error(request, "Parol kamida 8 ta belgidan iborat bo‘lishi kerak.", extra_tags='reset_password')
        else:
            student.set_password(password1)
            student.save()
            messages.success(request, "Parol muvaffaqiyatli tiklandi.", extra_tags='edit_user')
            return redirect('students_list_admin')

    return render(request, 'student-password.html', {
        'student': student
    })

@admin_required
def reset_teacher_password(request, teacher_id):

    teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if not password1 or not password2:
            messages.error(request, "Iltimos, barcha maydonlarni to‘ldiring.", extra_tags='reset_password_teacher')
        elif password1 != password2:
            messages.error(request, "Parollar mos kelmayapti.", extra_tags='reset_password_teacher')
        elif len(password1) < 8:
            messages.error(request, "Parol kamida 8 ta belgidan iborat bo‘lishi kerak.", extra_tags='reset_password_teacher')
        else:
            teacher.set_password(password1)
            teacher.save()
            messages.success(request, "Parol muvaffaqiyatli tiklandi.", extra_tags='teacher_list')
            return redirect('teachers_list_admin')

    return render(request, 'teacher-password.html', {
        'teacher': teacher
    })

from PIL import Image, ImageDraw

def make_circle_image(image_path, size_px=100):
    img = Image.open(image_path).convert("RGBA")
    img = img.resize((size_px, size_px))

    mask = Image.new("L", (size_px, size_px), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size_px, size_px), fill=255)

    img.putalpha(mask)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class OfficialNumberedCanvas(pdf_canvas.Canvas):
    """Rasmiy 2-bosqichli kolontitul kanvasi (Jami sahifalar soni va muassasa nomi bilan)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.site_title = "VLE TIZIMI"

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont(FONT_NAME, 8)
        self.setFillColor(colors.HexColor("#64748B"))
        # Pastki chegara chizig'i
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(15 * mm, 12 * mm, self._pagesize[0] - 15 * mm, 12 * mm)
        
        # Chap tomon matni
        doc_type = getattr(self, 'doc_type_title', "RASMIY RO'YXAT")
        title_text = f"{getattr(self, 'site_title', 'TIZIM').upper()} | {doc_type}"
        self.drawString(15 * mm, 7.5 * mm, title_text)
        
        # O'ng tomon: Sahifa X / Y
        self.drawRightString(self._pagesize[0] - 15 * mm, 7.5 * mm, f"Sahifa {self._pageNumber} / {page_count}")
        self.restoreState()


@subadmin_permission_required('manage_students')
def export_students_pdf(request):
    """
    O'quvchilar ro'yxatini rasmiy davlat va ta'lim muassasasi standartlariga mos
    (gerb/logotip, rekvizitlar, tasdiqlangan jadval, imzolar va muhr o'rni bilan)
    PDF hujjati shaklida eksport qilish.
    """
    group_id = request.GET.get('group_id')
    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"

    # Administrator ismi
    admin_user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(role='admin').first()
    if admin_user and (admin_user.first_name or admin_user.last_name):
        admin_name = f"{admin_user.first_name} {admin_user.last_name}".strip()
    else:
        admin_name = "Tizim Administratori"

    # 1. O'quvchilarni olish
    if group_id == "all" or not group_id:
        students = CustomUser.objects.filter(role='student').prefetch_related('student_groups').order_by('last_name', 'first_name')
        group_name = "Barcha o'quvchilar ro'yxati"
        subject_name = "Barcha fanlar"
        teachers_names = "Barcha o'qituvchilar"
        created_str = "-"
        doc_reg_id = f"OQ-ALL-{timezone.localtime(timezone.now()).strftime('%y%m%d%H%M')}"
        filename_prefix = "barcha_oquvchilar"
    else:
        try:
            group = Group.objects.prefetch_related('teachers', 'subject').get(id=group_id)
            students = group.students.all().prefetch_related('student_groups').order_by('last_name', 'first_name')
            group_name = f"{group.name} guruhi"
            subject_name = group.subject.name if group.subject else "-"
            teacher_list = group.teachers.all()
            teachers_names = ", ".join(f"{t.first_name} {t.last_name}".strip() for t in teacher_list) if teacher_list else "Biriktirilmagan"
            created_str = timezone.localtime(group.created_at).strftime("%d.%m.%Y %H:%M") if group.created_at else "-"
            doc_reg_id = f"OQ-G{group.id}-{timezone.localtime(timezone.now()).strftime('%y%m%d%H%M')}"
            filename_prefix = f"guruh_{group.id}"
        except Group.DoesNotExist:
            return HttpResponse("Guruh topilmadi", status=404)

    total_count = students.count()
    active_count = students.filter(is_active=True).count()
    inactive_count = students.filter(is_active=False).count()
    today_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")

    # 2. PDF hujjat parametrlarini sozlash
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm
    )
    elements = []
    styles = getSampleStyleSheet()

    # Tipografiya va uslublar
    title_main_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=3
    )
    title_sub_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0284C7'),
        alignment=1,
        spaceAfter=12
    )
    inst_name_style = ParagraphStyle(
        'InstName',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#0F172A')
    )
    inst_sub_style = ParagraphStyle(
        'InstSub',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748B')
    )
    reg_label_style = ParagraphStyle(
        'RegLabel',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#64748B'),
        alignment=2
    )
    reg_val_style = ParagraphStyle(
        'RegVal',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#0F172A'),
        alignment=2
    )
    meta_k_style = ParagraphStyle(
        'MetaK',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#475569')
    )
    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    td_center_style = ParagraphStyle(
        'TDCenter',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1E293B'),
        alignment=1
    )
    td_left_style = ParagraphStyle(
        'TDLeft',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1E293B'),
        alignment=0
    )
    td_left_bold_style = ParagraphStyle(
        'TDLeftBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0F172A'),
        alignment=0
    )
    status_active_style = ParagraphStyle(
        'StatusActive',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#059669'),
        alignment=1
    )
    status_blocked_style = ParagraphStyle(
        'StatusBlocked',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#DC2626'),
        alignment=1
    )

    # 3. Rasmiy bosh qism (Header Table: Tashkilot logotipi va nomi + Hujjat rekvizitlari)
    logo_cell = None
    if setting and setting.image and os.path.exists(setting.image.path):
        try:
            logo_buf = make_circle_image(setting.image.path, size_px=100)
            logo_cell = RLImage(logo_buf, width=16 * mm, height=16 * mm)
        except Exception:
            logo_cell = None

    if logo_cell:
        inst_block = Table([
            [logo_cell, [Paragraph(site_name.upper(), inst_name_style), Paragraph("O'QUV BO'LIMI VA MA'MURIYAT<br/>TA'LIM SIFATINI NAZORAT QILISH TIZIMI", inst_sub_style)]]
        ], colWidths=[20 * mm, 75 * mm])
        inst_block.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
    else:
        inst_block = Table([
            [[Paragraph(site_name.upper(), inst_name_style), Paragraph("O'QUV BO'LIMI VA MA'MURIYAT<br/>TA'LIM SIFATINI NAZORAT QILISH TIZIMI", inst_sub_style)]]
        ], colWidths=[95 * mm])
        inst_block.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

    req_block = [
        [Paragraph("HUJJAT TURI:", reg_label_style), Paragraph("Rasmiy qaydnoma", reg_val_style)],
        [Paragraph("QAYD RAQAMI:", reg_label_style), Paragraph(doc_reg_id, reg_val_style)],
        [Paragraph("SANA:", reg_label_style), Paragraph(today_str, reg_val_style)],
        [Paragraph("MAS'UL:", reg_label_style), Paragraph(admin_name, reg_val_style)],
    ]
    req_table = Table(req_block, colWidths=[35 * mm, 50 * mm])
    req_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    header_table = Table([[inst_block, req_table]], colWidths=[95 * mm, 85 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=10))

    # 4. Hujjat rasmiy sarlavhasi
    elements.append(Paragraph("O'QUVCHILAR RO'YXATI (QAYDNOMASI)", title_main_style))
    elements.append(Paragraph(f"{group_name.upper()} BO'YICHA BIRIKTIRILGAN TALABALAR VA O'QUVCHILAR", title_sub_style))

    # 5. Metadata va Statistika kartochkasi (2x4 jadval)
    meta_box_data = [
        [
            Paragraph(f"<b>Tashkilot:</b> {site_name}", meta_k_style),
            Paragraph(f"<b>Guruh / Kurs:</b> {group_name}", meta_k_style)
        ],
        [
            Paragraph(f"<b>Fan:</b> {subject_name}", meta_k_style),
            Paragraph(f"<b>O'qituvchi(lar):</b> {teachers_names}", meta_k_style)
        ],
        [
            Paragraph(f"<b>Jami o'quvchilar:</b> {total_count} nafar", meta_k_style),
            Paragraph(f"<b>Shundan faol:</b> {active_count} nafar | <b>Nofaol:</b> {inactive_count} nafar", meta_k_style)
        ],
        [
            Paragraph(f"<b>Guruh ochilgan sana:</b> {created_str}", meta_k_style),
            Paragraph(f"<b>Hujjat maqomi:</b> <font color='#059669'><b>Tasdiqlangan rasmiy ro'yxat</b></font>", meta_k_style)
        ]
    ]
    meta_box = Table(meta_box_data, colWidths=[90 * mm, 90 * mm])
    meta_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(meta_box)
    elements.append(Spacer(1, 10))

    # 6. O'quvchilar rasmiy jadvali (Kengligi: 180mm)
    col_widths = [10 * mm, 56 * mm, 32 * mm, 40 * mm, 20 * mm, 22 * mm]
    table_data = [[
        Paragraph("<b>№</b>", th_style),
        Paragraph("<b>F.I.SH.</b>", th_style),
        Paragraph("<b>Telefon raqami</b>", th_style),
        Paragraph("<b>Guruh(lar)i</b>", th_style),
        Paragraph("<b>Holati</b>", th_style),
        Paragraph("<b>Qo'shilgan sana</b>", th_style),
    ]]

    for idx, student in enumerate(students, start=1):
        full_name = f"{student.last_name} {student.first_name}".strip()
        groups_qs = student.student_groups.all()
        groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
        status_p = Paragraph("Faol", status_active_style) if student.is_active else Paragraph("Bloklangan", status_blocked_style)
        joined_str = timezone.localtime(student.joined_at).strftime("%d.%m.%Y") if student.joined_at else "-"

        table_data.append([
            Paragraph(str(idx), td_center_style),
            Paragraph(full_name, td_left_bold_style),
            Paragraph(student.phone_number or "-", td_center_style),
            Paragraph(groups_str, td_left_style),
            status_p,
            Paragraph(joined_str, td_center_style),
        ])

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#0284C7')),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 15))

    # 7. Imzo va muhr bloki (KeepTogether)
    stamp_element = Paragraph("<font color='#94A3B8'>[ M.O'. / Muhr o'rni ]</font>", td_center_style)
    if setting and setting.image and os.path.exists(setting.image.path):
        try:
            stamp_buf = make_circle_image(setting.image.path, size_px=110)
            stamp_element = RLImage(stamp_buf, width=24 * mm, height=24 * mm)
        except Exception:
            pass

    teacher_signature_title = "Mas'ul o'qituvchi / murabbiy:"
    teacher_signature_name = teachers_names if teachers_names != "Barcha o'qituvchilar" else "-"

    sign_data = [
        [
            Paragraph(f"<b>O'quv markaz rahbari:</b><br/>{admin_name}<br/><br/><br/>Imzo: ___________________", td_left_style),
            Paragraph(f"<b>{teacher_signature_title}</b><br/>{teacher_signature_name}<br/><br/><br/>Imzo: ___________________", td_left_style),
            stamp_element
        ]
    ]
    sign_table = Table(sign_data, colWidths=[65 * mm, 65 * mm, 50 * mm])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    legal_note = Paragraph("<i>Ushbu hujjat ta'lim muassasasining ichki elektron axborot tizimi orqali shakllantirilgan bo'lib, rasmiy hisobga olish hujjati hisoblanadi.</i>",
                           ParagraphStyle('LegalNote', parent=styles['Normal'], fontName=FONT_ITALIC, fontSize=7.5, leading=9.5, textColor=colors.HexColor('#64748B'), alignment=1))

    elements.append(KeepTogether([
        sign_table,
        Spacer(1, 10),
        legal_note
    ]))

    # 8. Hujjatni yig'ish (NumberedCanvas bilan)
    def make_canvas(title):
        class CustomCanvas(OfficialNumberedCanvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.site_title = title
        return CustomCanvas

    doc.build(elements, canvasmaker=make_canvas(site_name))
    buffer.seek(0)

    filename = f"rasmiy_royxat_{filename_prefix}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@subadmin_permission_required('manage_students')
def export_students_excel(request):
    """
    O'quvchilar ro'yxatini to'liq formatlangan, rangli sarlavha va katakchalarga ega
    professional Excel (.xlsx) fayli ko'rinishida yuklab olish.
    """
    group_id = request.GET.get('group_id')
    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"

    # Administrator ismi
    admin_user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(role='admin').first()
    if admin_user and (admin_user.first_name or admin_user.last_name):
        admin_name = f"{admin_user.first_name} {admin_user.last_name}".strip()
    else:
        admin_name = "Tizim Administratori"

    # 1. O'quvchilarni olish
    if group_id == "all" or not group_id:
        students = CustomUser.objects.filter(role='student').prefetch_related('student_groups').order_by('last_name', 'first_name')
        group_name = "Barcha o'quvchilar ro'yxati"
        subject_name = "Barcha fanlar"
        teachers_names = "Barcha o'qituvchilar"
        filename_prefix = "barcha_oquvchilar"
    else:
        try:
            group = Group.objects.prefetch_related('teachers', 'subject').get(id=group_id)
            students = group.students.all().prefetch_related('student_groups').order_by('last_name', 'first_name')
            group_name = f"{group.name} guruhi"
            subject_name = group.subject.name if group.subject else "-"
            teacher_list = group.teachers.all()
            teachers_names = ", ".join(f"{t.first_name} {t.last_name}".strip() for t in teacher_list) if teacher_list else "Biriktirilmagan"
            filename_prefix = f"guruh_{group.id}"
        except Group.DoesNotExist:
            return HttpResponse("Guruh topilmadi", status=404)

    total_count = students.count()
    active_count = students.filter(is_active=True).count()
    inactive_count = students.filter(is_active=False).count()
    today_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")

    # 2. OpenPyXL kutubxonasini tekshirish va Workbook yaratish
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "O'quvchilar"
    except ImportError:
        # Agar openpyxl kutubxonasi mavjud bo'lmasa, UTF-8 BOM bilan CSV formatida yuklab berish
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="oquvchilar_{filename_prefix}_{timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")}.csv"'
        writer = csv.writer(response)
        writer.writerow([f"{site_name.upper()} - O'QUVCHILAR RO'YXATI (QAYDNOMASI)"])
        writer.writerow([f"Guruh: {group_name}", f"Fan: {subject_name}", f"O'qituvchi: {teachers_names}", f"Sana: {today_str}"])
        writer.writerow([])
        writer.writerow(["№", "Familiyasi", "Ismi", "Telefon raqami", "Logini (Username)", "Guruh(lar)i", "Holati", "Qo'shilgan sana"])
        for idx, student in enumerate(students, start=1):
            groups_qs = student.student_groups.all()
            groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
            status_text = "Faol" if student.is_active else "Bloklangan"
            joined_str = timezone.localtime(student.joined_at).strftime("%d.%m.%Y %H:%M") if student.joined_at else "-"
            writer.writerow([idx, student.last_name, student.first_name, student.phone_number or "-", student.username, groups_str, status_text, joined_str])
        return response


    # Chiziqlar va stillar
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    summary_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    font_title = Font(name="Arial", size=13, bold=True, color="0F172A")
    font_sub = Font(name="Arial", size=10, bold=True, color="0284C7")
    font_meta = Font(name="Arial", size=9.5, italic=True, color="475569")
    font_th = Font(name="Arial", size=10.5, bold=True, color="FFFFFF")
    font_td = Font(name="Arial", size=10, color="1E293B")
    font_td_bold = Font(name="Arial", size=10, bold=True, color="0F172A")
    font_active = Font(name="Arial", size=10, bold=True, color="059669")
    font_blocked = Font(name="Arial", size=10, bold=True, color="DC2626")
    font_summary = Font(name="Arial", size=10.5, bold=True, color="0F172A")

    # Sarlavha qatorlari
    ws.merge_cells("A1:H1")
    ws["A1"] = f"{site_name.upper()} - O'QUVCHILAR RO'YXATI (QAYDNOMASI)"
    ws["A1"].font = font_title
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:H2")
    ws["A2"] = f"Guruh / Kurs: {group_name} | Fan: {subject_name} | O'qituvchi(lar): {teachers_names}"
    ws["A2"].font = font_sub
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    ws.merge_cells("A3:H3")
    ws["A3"] = f"Shakllantirildi: {today_str} | Jami: {total_count} nafar (Faol: {active_count} ta, Bloklangan: {inactive_count} ta) | Mas'ul: {admin_name}"
    ws["A3"].font = font_meta
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 18

    # Qator 4 bo'sh (ajratuvchi)
    ws.row_dimensions[4].height = 8

    # Ustun sarlavhalari (Row 5)
    headers = [
        "№",
        "Familiyasi",
        "Ismi",
        "Telefon raqami",
        "Logini (Username)",
        "Guruh(lar)i",
        "Holati",
        "Qo'shilgan sana"
    ]

    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_num)
        cell.value = header_title
        cell.font = font_th
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[5].height = 24

    # Ma'lumot qatorlari
    current_row = 6
    for idx, student in enumerate(students, start=1):
        groups_qs = student.student_groups.all()
        groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
        status_text = "Faol" if student.is_active else "Bloklangan"
        joined_str = timezone.localtime(student.joined_at).strftime("%d.%m.%Y %H:%M") if student.joined_at else "-"

        row_values = [
            idx,
            student.last_name,
            student.first_name,
            student.phone_number or "-",
            student.username,
            groups_str,
            status_text,
            joined_str
        ]

        is_even = (idx % 2 == 0)

        for col_num, val in enumerate(row_values, 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.value = val
            cell.border = thin_border

            if is_even:
                cell.fill = alt_fill

            # Formatlash
            if col_num == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td
            elif col_num in (2, 3):
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.font = font_td_bold
            elif col_num == 4:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td
            elif col_num == 5:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td
            elif col_num == 6:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.font = font_td
            elif col_num == 7:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_active if student.is_active else font_blocked
            elif col_num == 8:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    # Jamlama qator (Summary row)
    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
    summary_cell = ws.cell(row=current_row, column=1)
    summary_cell.value = f"JAMI O'QUVCHILAR: {total_count} nafar  (Faol: {active_count} ta, Bloklangan: {inactive_count} ta)"
    summary_cell.font = font_summary
    summary_cell.fill = summary_fill
    summary_cell.alignment = Alignment(horizontal="center", vertical="center")
    for c in range(1, 9):
        ws.cell(row=current_row, column=c).border = thin_border
    ws.row_dimensions[current_row].height = 22
    current_row += 2

    # Imzolar bloki
    ws.cell(row=current_row, column=2, value=f"O'quv markaz rahbari: {admin_name}").font = font_td_bold
    ws.cell(row=current_row, column=5, value=f"Mas'ul o'qituvchi: {teachers_names}").font = font_td_bold
    ws.cell(row=current_row, column=8, value="M.O'.").font = font_td_bold

    current_row += 1
    ws.cell(row=current_row, column=2, value="Imzo: ___________________").font = font_meta
    ws.cell(row=current_row, column=5, value="Imzo: ___________________").font = font_meta

    # Ustunlar kengligini o'rnatish
    ws.column_dimensions['A'].width = 8   # №
    ws.column_dimensions['B'].width = 18  # Familiya
    ws.column_dimensions['C'].width = 18  # Ism
    ws.column_dimensions['D'].width = 18  # Telefon
    ws.column_dimensions['E'].width = 18  # Login
    ws.column_dimensions['F'].width = 24  # Guruhlari
    ws.column_dimensions['G'].width = 14  # Holati
    ws.column_dimensions['H'].width = 20  # Qo'shilgan sana

    # Gridlines yoqish
    ws.views.sheetView[0].showGridLines = True

    filename = f"oquvchilar_{filename_prefix}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@subadmin_permission_required('manage_teachers')
def export_teachers_pdf(request):
    """
    O'qituvchilar ro'yxatini rasmiy davlat va ta'lim muassasasi standartlariga mos
    (gerb/logotip, rekvizitlar, tasdiqlangan jadval, imzolar va muhr o'rni bilan)
    PDF hujjati shaklida eksport qilish.
    """
    subject_id = request.GET.get('subject_id')
    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"

    # Administrator ismi
    admin_user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(role='admin').first()
    if admin_user and (admin_user.first_name or admin_user.last_name):
        admin_name = f"{admin_user.first_name} {admin_user.last_name}".strip()
    else:
        admin_name = "Tizim Administratori"

    # 1. O'qituvchilarni olish
    if subject_id == "all" or not subject_id:
        teachers = CustomUser.objects.filter(role='teacher').prefetch_related('subjects', 'teachers_groups').order_by('last_name', 'first_name')
        category_name = "Barcha o'qituvchilar ro'yxati"
        subject_name = "Barcha fanlar / mutaxassisliklar"
        doc_reg_id = f"OQT-ALL-{timezone.localtime(timezone.now()).strftime('%y%m%d%H%M')}"
        filename_prefix = "barcha_oqituvchilar"
    else:
        try:
            subject = Subject.objects.get(id=subject_id)
            teachers = CustomUser.objects.filter(role='teacher', subjects=subject).prefetch_related('subjects', 'teachers_groups').order_by('last_name', 'first_name')
            category_name = f"{subject.name} fani o'qituvchilari"
            subject_name = subject.name
            doc_reg_id = f"OQT-S{subject.id}-{timezone.localtime(timezone.now()).strftime('%y%m%d%H%M')}"
            filename_prefix = f"fan_{subject.id}"
        except Subject.DoesNotExist:
            return HttpResponse("Fan topilmadi", status=404)

    total_count = teachers.count()
    active_count = teachers.filter(is_active=True).count()
    inactive_count = teachers.filter(is_active=False).count()
    today_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")

    # 2. PDF hujjat parametrlarini sozlash
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm
    )
    elements = []
    styles = getSampleStyleSheet()

    # Tipografiya va uslublar
    title_main_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=3
    )
    title_sub_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0284C7'),
        alignment=1,
        spaceAfter=12
    )
    inst_name_style = ParagraphStyle(
        'InstName',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#0F172A')
    )
    inst_sub_style = ParagraphStyle(
        'InstSub',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748B')
    )
    reg_label_style = ParagraphStyle(
        'RegLabel',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#64748B'),
        alignment=2
    )
    reg_val_style = ParagraphStyle(
        'RegVal',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#0F172A'),
        alignment=2
    )
    meta_k_style = ParagraphStyle(
        'MetaK',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#475569')
    )
    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    td_center_style = ParagraphStyle(
        'TDCenter',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1E293B'),
        alignment=1
    )
    td_left_style = ParagraphStyle(
        'TDLeft',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1E293B'),
        alignment=0
    )
    td_left_bold_style = ParagraphStyle(
        'TDLeftBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0F172A'),
        alignment=0
    )
    status_active_style = ParagraphStyle(
        'StatusActive',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#059669'),
        alignment=1
    )
    status_blocked_style = ParagraphStyle(
        'StatusBlocked',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#DC2626'),
        alignment=1
    )

    # 3. Rasmiy bosh qism (Header Table)
    logo_cell = None
    if setting and setting.image and os.path.exists(setting.image.path):
        try:
            logo_buf = make_circle_image(setting.image.path, size_px=100)
            logo_cell = RLImage(logo_buf, width=16 * mm, height=16 * mm)
        except Exception:
            logo_cell = None

    if logo_cell:
        inst_block = Table([
            [logo_cell, [Paragraph(site_name.upper(), inst_name_style), Paragraph("O'QUV BO'LIMI VA PEDAGOGIK TARKIB<br/>ILMIY-METODIK NAZORAT TIZIMI", inst_sub_style)]]
        ], colWidths=[20 * mm, 75 * mm])
        inst_block.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
    else:
        inst_block = Table([
            [[Paragraph(site_name.upper(), inst_name_style), Paragraph("O'QUV BO'LIMI VA PEDAGOGIK TARKIB<br/>ILMIY-METODIK NAZORAT TIZIMI", inst_sub_style)]]
        ], colWidths=[95 * mm])
        inst_block.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

    req_block = [
        [Paragraph("HUJJAT TURI:", reg_label_style), Paragraph("Pedagogik qaydnoma", reg_val_style)],
        [Paragraph("QAYD RAQAMI:", reg_label_style), Paragraph(doc_reg_id, reg_val_style)],
        [Paragraph("SANA:", reg_label_style), Paragraph(today_str, reg_val_style)],
        [Paragraph("MAS'UL:", reg_label_style), Paragraph(admin_name, reg_val_style)],
    ]
    req_table = Table(req_block, colWidths=[35 * mm, 50 * mm])
    req_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    header_table = Table([[inst_block, req_table]], colWidths=[95 * mm, 85 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=10))

    # 4. Hujjat rasmiy sarlavhasi
    elements.append(Paragraph("O'QITUVCHILAR VA PEDAGOGLAR RO'YXATI", title_main_style))
    elements.append(Paragraph(f"{category_name.upper()} BO'YICHA BIRIKTIRILGAN O'QITUVCHILAR REYESTRI", title_sub_style))

    # 5. Metadata va Statistika kartochkasi
    meta_box_data = [
        [
            Paragraph(f"<b>Tashkilot:</b> {site_name}", meta_k_style),
            Paragraph(f"<b>Kategoriya:</b> {category_name}", meta_k_style)
        ],
        [
            Paragraph(f"<b>Fan / Mutaxassislik:</b> {subject_name}", meta_k_style),
            Paragraph(f"<b>Hujjat maqomi:</b> <font color='#059669'><b>Tasdiqlangan pedagoglar ro'yxati</b></font>", meta_k_style)
        ],
        [
            Paragraph(f"<b>Jami o'qituvchilar:</b> {total_count} nafar", meta_k_style),
            Paragraph(f"<b>Shundan faol:</b> {active_count} nafar | <b>Nofaol:</b> {inactive_count} nafar", meta_k_style)
        ]
    ]
    meta_box = Table(meta_box_data, colWidths=[90 * mm, 90 * mm])
    meta_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(meta_box)
    elements.append(Spacer(1, 10))

    # 6. O'qituvchilar rasmiy jadvali (Kengligi: 180mm)
    col_widths = [10 * mm, 46 * mm, 28 * mm, 38 * mm, 38 * mm, 20 * mm]
    table_data = [[
        Paragraph("<b>№</b>", th_style),
        Paragraph("<b>F.I.SH.</b>", th_style),
        Paragraph("<b>Telefon raqami</b>", th_style),
        Paragraph("<b>Fan / Mutaxassisliklari</b>", th_style),
        Paragraph("<b>Guruh(lar)i</b>", th_style),
        Paragraph("<b>Holati</b>", th_style),
    ]]

    for idx, teacher in enumerate(teachers, start=1):
        full_name = f"{teacher.last_name} {teacher.first_name}".strip()
        subjects_qs = teacher.subjects.all()
        subjects_str = ", ".join(s.name for s in subjects_qs) if subjects_qs else "-"
        groups_qs = teacher.teachers_groups.all()
        groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
        status_p = Paragraph("Faol", status_active_style) if teacher.is_active else Paragraph("Bloklangan", status_blocked_style)

        table_data.append([
            Paragraph(str(idx), td_center_style),
            Paragraph(full_name, td_left_bold_style),
            Paragraph(teacher.phone_number or "-", td_center_style),
            Paragraph(subjects_str, td_left_style),
            Paragraph(groups_str, td_left_style),
            status_p,
        ])

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#0284C7')),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 15))

    # 7. Imzo va muhr bloki
    stamp_element = Paragraph("<font color='#94A3B8'>[ M.O'. / Muhr o'rni ]</font>", td_center_style)
    if setting and setting.image and os.path.exists(setting.image.path):
        try:
            stamp_buf = make_circle_image(setting.image.path, size_px=110)
            stamp_element = RLImage(stamp_buf, width=24 * mm, height=24 * mm)
        except Exception:
            pass

    sign_data = [
        [
            Paragraph(f"<b>O'quv markaz rahbari:</b><br/>{admin_name}<br/><br/><br/>Imzo: ___________________", td_left_style),
            Paragraph(f"<b>O'quv-metodik bo'lim boshlig'i:</b><br/>{admin_name}<br/><br/><br/>Imzo: ___________________", td_left_style),
            stamp_element
        ]
    ]
    sign_table = Table(sign_data, colWidths=[65 * mm, 65 * mm, 50 * mm])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    legal_note = Paragraph("<i>Ushbu hujjat ta'lim muassasasining ichki elektron axborot tizimi orqali shakllantirilgan bo'lib, rasmiy hisobga olish hujjati hisoblanadi.</i>",
                           ParagraphStyle('LegalNote', parent=styles['Normal'], fontName=FONT_ITALIC, fontSize=7.5, leading=9.5, textColor=colors.HexColor('#64748B'), alignment=1))

    elements.append(KeepTogether([
        sign_table,
        Spacer(1, 10),
        legal_note
    ]))

    def make_canvas(title):
        class CustomCanvas(OfficialNumberedCanvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.site_title = title
                self.doc_type_title = "RASMIY O'QITUVCHILAR RO'YXATI"
        return CustomCanvas

    doc.build(elements, canvasmaker=make_canvas(site_name))
    buffer.seek(0)

    filename = f"rasmiy_oqituvchilar_{filename_prefix}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@subadmin_permission_required('manage_teachers')
def export_teachers_excel(request):
    """
    O'qituvchilar ro'yxatini to'liq formatlangan, rangli sarlavha va katakchalarga ega
    professional Excel (.xlsx) fayli ko'rinishida yuklab olish.
    """
    subject_id = request.GET.get('subject_id')
    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"

    # Administrator ismi
    admin_user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(role='admin').first()
    if admin_user and (admin_user.first_name or admin_user.last_name):
        admin_name = f"{admin_user.first_name} {admin_user.last_name}".strip()
    else:
        admin_name = "Tizim Administratori"

    # 1. O'qituvchilarni olish
    if subject_id == "all" or not subject_id:
        teachers = CustomUser.objects.filter(role='teacher').prefetch_related('subjects', 'teachers_groups').order_by('last_name', 'first_name')
        category_name = "Barcha o'qituvchilar ro'yxati"
        subject_name = "Barcha fanlar / mutaxassisliklar"
        filename_prefix = "barcha_oqituvchilar"
    else:
        try:
            subject = Subject.objects.get(id=subject_id)
            teachers = CustomUser.objects.filter(role='teacher', subjects=subject).prefetch_related('subjects', 'teachers_groups').order_by('last_name', 'first_name')
            category_name = f"{subject.name} fani o'qituvchilari"
            subject_name = subject.name
            filename_prefix = f"fan_{subject.id}"
        except Subject.DoesNotExist:
            return HttpResponse("Fan topilmadi", status=404)

    total_count = teachers.count()
    active_count = teachers.filter(is_active=True).count()
    inactive_count = teachers.filter(is_active=False).count()
    today_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")

    # 2. OpenPyXL kutubxonasini tekshirish va Workbook yaratish
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "O'qituvchilar"
    except ImportError:
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="oqituvchilar_{filename_prefix}_{timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")}.csv"'
        writer = csv.writer(response)
        writer.writerow([f"{site_name.upper()} - O'QITUVCHILAR RO'YXATI (QAYDNOMASI)"])
        writer.writerow([f"Kategoriya: {category_name}", f"Fan: {subject_name}", f"Sana: {today_str}"])
        writer.writerow([])
        writer.writerow(["№", "Familiyasi", "Ismi", "Telefon raqami", "Logini (Username)", "Fan / Mutaxassisliklari", "Guruh(lar)i", "Holati", "Qo'shilgan sana"])
        for idx, teacher in enumerate(teachers, start=1):
            subjects_qs = teacher.subjects.all()
            subjects_str = ", ".join(s.name for s in subjects_qs) if subjects_qs else "-"
            groups_qs = teacher.teachers_groups.all()
            groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
            status_text = "Faol" if teacher.is_active else "Bloklangan"
            joined_str = timezone.localtime(teacher.joined_at).strftime("%d.%m.%Y %H:%M") if teacher.joined_at else "-"
            writer.writerow([idx, teacher.last_name, teacher.first_name, teacher.phone_number or "-", teacher.username, subjects_str, groups_str, status_text, joined_str])
        return response

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    summary_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    font_title = Font(name="Arial", size=13, bold=True, color="0F172A")
    font_sub = Font(name="Arial", size=10, bold=True, color="0284C7")
    font_meta = Font(name="Arial", size=9.5, italic=True, color="475569")
    font_th = Font(name="Arial", size=10.5, bold=True, color="FFFFFF")
    font_td = Font(name="Arial", size=10, color="1E293B")
    font_td_bold = Font(name="Arial", size=10, bold=True, color="0F172A")
    font_active = Font(name="Arial", size=10, bold=True, color="059669")
    font_blocked = Font(name="Arial", size=10, bold=True, color="DC2626")
    font_summary = Font(name="Arial", size=10.5, bold=True, color="0F172A")

    # Sarlavha qatorlari
    ws.merge_cells("A1:I1")
    ws["A1"] = f"{site_name.upper()} - O'QITUVCHILAR RO'YXATI (QAYDNOMASI)"
    ws["A1"].font = font_title
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:I2")
    ws["A2"] = f"Kategoriya: {category_name} | Fan / Mutaxassislik: {subject_name}"
    ws["A2"].font = font_sub
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    ws.merge_cells("A3:I3")
    ws["A3"] = f"Shakllantirildi: {today_str} | Jami: {total_count} nafar (Faol: {active_count} ta, Bloklangan: {inactive_count} ta) | Mas'ul: {admin_name}"
    ws["A3"].font = font_meta
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 18

    ws.row_dimensions[4].height = 8

    headers = [
        "№",
        "Familiyasi",
        "Ismi",
        "Telefon raqami",
        "Logini (Username)",
        "Fan / Mutaxassisliklari",
        "Guruh(lar)i",
        "Holati",
        "Qo'shilgan sana"
    ]

    for col_num, header_title in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_num)
        cell.value = header_title
        cell.font = font_th
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[5].height = 24

    current_row = 6
    for idx, teacher in enumerate(teachers, start=1):
        subjects_qs = teacher.subjects.all()
        subjects_str = ", ".join(s.name for s in subjects_qs) if subjects_qs else "-"
        groups_qs = teacher.teachers_groups.all()
        groups_str = ", ".join(g.name for g in groups_qs) if groups_qs else "-"
        status_text = "Faol" if teacher.is_active else "Bloklangan"
        joined_str = timezone.localtime(teacher.joined_at).strftime("%d.%m.%Y %H:%M") if teacher.joined_at else "-"

        row_values = [
            idx,
            teacher.last_name,
            teacher.first_name,
            teacher.phone_number or "-",
            teacher.username,
            subjects_str,
            groups_str,
            status_text,
            joined_str
        ]

        is_even = (idx % 2 == 0)

        for col_num, val in enumerate(row_values, 1):
            cell = ws.cell(row=current_row, column=col_num)
            cell.value = val
            cell.border = thin_border

            if is_even:
                cell.fill = alt_fill

            if col_num == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td
            elif col_num in (2, 3):
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.font = font_td_bold
            elif col_num in (4, 5):
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td
            elif col_num in (6, 7):
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.font = font_td
            elif col_num == 8:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_active if teacher.is_active else font_blocked
            elif col_num == 9:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_td

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=9)
    summary_cell = ws.cell(row=current_row, column=1)
    summary_cell.value = f"JAMI O'QITUVCHILAR: {total_count} nafar  (Faol: {active_count} ta, Bloklangan: {inactive_count} ta)"
    summary_cell.font = font_summary
    summary_cell.fill = summary_fill
    summary_cell.alignment = Alignment(horizontal="center", vertical="center")
    for c in range(1, 10):
        ws.cell(row=current_row, column=c).border = thin_border
    ws.row_dimensions[current_row].height = 22
    current_row += 2

    ws.cell(row=current_row, column=2, value=f"O'quv markaz rahbari: {admin_name}").font = font_td_bold
    ws.cell(row=current_row, column=6, value=f"O'quv-metodik bo'lim boshlig'i: {admin_name}").font = font_td_bold
    ws.cell(row=current_row, column=9, value="M.O'.").font = font_td_bold

    current_row += 1
    ws.cell(row=current_row, column=2, value="Imzo: ___________________").font = font_meta
    ws.cell(row=current_row, column=6, value="Imzo: ___________________").font = font_meta

    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 18
    ws.column_dimensions['F'].width = 24
    ws.column_dimensions['G'].width = 24
    ws.column_dimensions['H'].width = 14
    ws.column_dimensions['I'].width = 20

    ws.views.sheetView[0].showGridLines = True

    filename = f"oqituvchilar_{filename_prefix}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response





DAYS_ORDER = [day[0] for day in DAYS_OF_WEEK]
DAY_NAMES = dict(DAYS_OF_WEEK)

@subadmin_permission_required('manage_schedules')
@transaction.atomic
def edit_group_teacher_schedule(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    teachers = group.teachers.all()
    days = DAYS_OF_WEEK

    if request.method == 'POST':
        validation_errors = []
        for teacher in teachers:
            for day_value, _ in days:
                input_values = request.POST.getlist(f"schedule-{teacher.id}-{day_value}")
                for time_str in input_values:
                    time_str = time_str.strip()
                    if not time_str or '(' in time_str:
                        continue
                    
                    if '-' not in time_str:
                        validation_errors.append(f"Noto'g'ri format: '{time_str}'. Iltimos, dars vaqtini 'HH:MM - HH:MM' formatida kiriting (Masalan: 14:00 - 16:00)")
                        continue
                    
                    try:
                        start_str, end_str = [s.strip() for s in time_str.split('-')]
                        start_time = datetime.strptime(start_str, "%H:%M").time()
                        end_time = datetime.strptime(end_str, "%H:%M").time()
                        if start_time >= end_time:
                            validation_errors.append(f"Xato: Boshlanish vaqti ({start_str}) tugash vaqtidan ({end_str}) oldin bo'lishi shart!")
                    except ValueError:
                        validation_errors.append(f"Noto'g'ri vaqt qiymati: '{time_str}'. Iltimos, soat (00-23) va daqiqa (00-59) oraliqlarida to'g'ri kiriting (Masalan: 14:00 - 16:00)")

        if validation_errors:
            for err in validation_errors:
                messages.error(request, err)
            return redirect('edit_group_teacher_schedule', group_id=group.id)

        # Hamma ma'lumotlar to'g'ri bo'lsagina saqlaymiz.
        # Barcha dars jadvallarini to'g'ridan-to'g'ri o'chirib tashlamaymiz (chunki bu botga qolgan o'zgarmagan kunlar ham o'chirildi degan noto'g'ri xabar borishiga sabab bo'ladi).
        # Buning o'rniga aniq solishtirib: faqat vaqti o'zgarganini update qilamiz, yangisini create qilamiz, o'chirilganini delete qilamiz.
        for teacher in teachers:
            for day_value, _ in days:
                existing_day_schedules = list(
                    Schedule.objects.filter(group=group, teacher=teacher, day=day_value).order_by('start_time')
                )

                input_values = request.POST.getlist(f"schedule-{teacher.id}-{day_value}")
                new_times = []
                for time_str in input_values:
                    time_str = time_str.strip()
                    if not time_str or '(' in time_str:
                        continue
                    try:
                        start_str, end_str = [s.strip() for s in time_str.split('-')]
                        st = datetime.strptime(start_str, "%H:%M").time()
                        et = datetime.strptime(end_str, "%H:%M").time()
                        new_times.append((st, et))
                    except ValueError:
                        pass

                # Vaqtlarni tartiblash va takroriy kiritilganlarini tozalash
                new_times = sorted(list(dict.fromkeys(new_times)), key=lambda x: (x[0], x[1]))

                # 1-bosqich: Umuman o'zgarmagan (vaqtlari aynan bir xil) jadvallarni ajratish
                for nt in list(new_times):
                    match = next(
                        (s for s in existing_day_schedules if s.start_time == nt[0] and s.end_time == nt[1]),
                        None
                    )
                    if match:
                        existing_day_schedules.remove(match)
                        new_times.remove(nt)
                        # Bu darsga tegilmaydi va hech qanday ortiqcha xabar jo'natilmaydi!

                # 2-bosqich: Vaqti o'zgartirilgan darslarni yangilash
                while existing_day_schedules and new_times:
                    s = existing_day_schedules.pop(0)
                    new_st, new_et = new_times.pop(0)
                    s.start_time = new_st
                    s.end_time = new_et
                    s.save()

                # 3-bosqich: Yangi qo'shilgan darslarni yaratish
                for new_st, new_et in new_times:
                    Schedule.objects.create(
                        group=group,
                        teacher=teacher,
                        day=day_value,
                        start_time=new_st,
                        end_time=new_et
                    )

                # 4-bosqich: Formadan olib tashlangan (o'chirilgan) darslarni o'chirish
                for s in existing_day_schedules:
                    s.delete()

        messages.success(request, "Dars jadvali muvaffaqiyatli saqlandi.")
        return redirect('edit_group_teacher_schedule', group_id=group.id)

    # GET so‘rov: jadvalni tuzish
    schedule_map = {teacher.id: {day[0]: [] for day in days} for teacher in teachers}

    # 1. Shu guruhdagi o‘qituvchilarning ushbu guruhdagi darslari
    for schedule in Schedule.objects.filter(group=group, teacher__in=teachers):
        schedule_map[schedule.teacher.id][schedule.day].append({
            'time': f"{schedule.start_time.strftime('%H:%M')} - {schedule.end_time.strftime('%H:%M')}",
            'readonly': False,
            'group_name': group.name
        })

    # 2. Boshqa guruhlaridagi darslar (readonly)
    other_schedules = Schedule.objects.exclude(group=group).filter(teacher__in=teachers)
    for schedule in other_schedules:
        schedule_map[schedule.teacher.id][schedule.day].append({
            'time': f"{schedule.start_time.strftime('%H:%M')} - {schedule.end_time.strftime('%H:%M')}",
            'readonly': True,
            'group_name': schedule.group.name  # boshqa guruh nomi
        })

    context = {
        'group': group,
        'teachers': teachers,
        'days': days,
        'day_names': DAY_NAMES,
        'schedule_map': schedule_map,
    }

    return render(request, 'edit_group_teacher_schedule.html', context)



@subadmin_permission_required('manage_schedules')
def all_group_schedules_view(request):
    groups = Group.objects.all().select_related('subject').prefetch_related('teachers')
    schedules = Schedule.objects.select_related('group', 'teacher', 'group__subject').order_by('group', 'day', 'start_time')

    group_schedules = {}
    for schedule in schedules:
        group = schedule.group
        if group not in group_schedules:
            group_schedules[group] = []
        group_schedules[group].append(schedule)

    for group in groups:
        if group not in group_schedules:
            group_schedules[group] = []

    return render(request, 'all_group_schedules.html', {
        'group_schedules': group_schedules,
    })



@subadmin_permission_required('manage_schedules')
@require_POST
def delete_schedule_view(request):
    group_id = request.POST.get('group_id')
    day = request.POST.get('day')
    start_time = request.POST.get('start_time')

    if not all([group_id, day, start_time]):
        messages.error(request, "Ma'lumotlar to‘liq emas.")
        return redirect('all_group_schedules')

    try:
        group = get_object_or_404(Group, id=group_id)

        deleted, _ = Schedule.objects.filter(
            group=group,
            day=day,
            start_time=start_time
        ).delete()

        if deleted:
            messages.success(request, "Dars jadvali muvaffaqiyatli o‘chirildi.")
        else:
            messages.warning(request, "Bunday dars jadvali topilmadi.")

    except Exception as e:
        messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return redirect('all_group_schedules')



@subadmin_permission_required('manage_assignments')
def add_topshiriq(request):

    if request.method == 'POST':
        title = request.POST.get('title')
        group_id = request.POST.get('group_id')
        teacher_id = request.POST.get('teacher_id')
        deadline = parse_datetime(request.POST.get('deadline'))
        max_score = request.POST.get('max_score')
        file = request.FILES.get('file')

        if not all([title, group_id, teacher_id, deadline, max_score, file]):
            messages.error(request, "Hamma maydonlarni to‘ldiring!")
            return redirect('add_topshiriq')

        if file:
            from main.validators import validate_document_file
            from django.core.exceptions import ValidationError
            try:
                validate_document_file(file)
            except ValidationError as ve:
                messages.error(request, ve.message)
                return redirect('add_topshiriq')

        group = Group.objects.get(id=group_id)
        teacher = CustomUser.objects.get(id=teacher_id)

        parsed_deadline = parse_datetime(deadline) if isinstance(deadline, str) else deadline
        if not parsed_deadline and isinstance(deadline, str):
            try:
                parsed_deadline = datetime.fromisoformat(deadline)
            except Exception:
                pass
        if parsed_deadline and timezone.is_naive(parsed_deadline):
            parsed_deadline = timezone.make_aware(parsed_deadline, timezone.get_current_timezone())

        Assignment.objects.create(
            title=title,
            group=group,
            teacher=teacher,
            deadline=parsed_deadline or deadline,
            max_score=max_score,
            file=file
        )

        messages.success(request, "Topshiriq muvaffaqiyatli yaratildi!")
        return redirect('admin_assignment_list')  # topshiriq ro'yxatiga qaytish

    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')

    return render(request, 'add-topshiriq.html', {
        'groups': groups,
        'teachers': teachers
    })


@subadmin_permission_required('manage_assignments')
def admin_assignment_list(request):

    assignments = Assignment.objects.all().order_by('-created_at')
    return render(request, 'admin-topshiriq-list.html', {'assignments': assignments})


@subadmin_permission_required('manage_assignments')
def edit_topshiriq(request, assignment_id):

    assignment = get_object_or_404(Assignment, id=assignment_id)

    if request.method == 'POST':

        if not all([request.POST.get('title'),
                    request.POST.get('group_id'),
                    request.POST.get('teacher_id'),
                    request.POST.get('deadline'),
                    request.POST.get('max_score')]):
            messages.error(request, "Hamma maydonlarni to‘ldiring!")
            return redirect('edit_topshiriq')

        deadline_raw = request.POST.get('deadline')
        parsed_deadline = parse_datetime(deadline_raw) if isinstance(deadline_raw, str) else deadline_raw
        if not parsed_deadline and isinstance(deadline_raw, str):
            try:
                parsed_deadline = datetime.fromisoformat(deadline_raw)
            except Exception:
                pass
        if parsed_deadline and timezone.is_naive(parsed_deadline):
            parsed_deadline = timezone.make_aware(parsed_deadline, timezone.get_current_timezone())

        assignment.title = request.POST.get('title')
        assignment.group = Group.objects.get(id=request.POST.get('group_id'))
        assignment.teacher = CustomUser.objects.get(id=request.POST.get('teacher_id'))
        assignment.deadline = parsed_deadline or deadline_raw
        assignment.max_score = request.POST.get('max_score')

        if 'file' in request.FILES:
            new_file = request.FILES['file']
            from main.validators import validate_document_file
            from django.core.exceptions import ValidationError
            try:
                validate_document_file(new_file)
            except ValidationError as ve:
                messages.error(request, ve.message)
                return redirect('edit_topshiriq', assignment_id=assignment.id)

            # ✅ Eski faylni o‘chirish
            if assignment.file:
                old_file_path = assignment.file.path
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            # ✅ Yangi faylni saqlash
            assignment.file = new_file

        assignment.save()
        return redirect('admin_assignment_list')

    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')

    return render(request, 'edit-topshiriq-admin.html', {
        'assignment': assignment,
        'groups': groups,
        'teachers': teachers
    })

@subadmin_permission_required('manage_assignments')
def admin_delete_assignment(request, assignment_id):

    assignment = get_object_or_404(Assignment, id=assignment_id)

    # Faylni diskdan o‘chirish
    if assignment.file:
        file_path = assignment.file.path
        if os.path.exists(file_path):
            os.remove(file_path)

    assignment.delete()
    messages.success(request, "Topshiriq muvaffaqiyatli o‘chirildi.")
    return redirect('admin_assignment_list')


@subadmin_permission_required('manage_quizzes')
@transaction.atomic
def add_test_admin(request):
    if request.method == 'POST':
        quiz_id = request.POST.get('quiz')
        question_text = request.POST.get('question_text')

        # Quiz obyektini topamiz
        try:
            quiz = Quiz.objects.get(id=quiz_id)
        except Quiz.DoesNotExist:
            return HttpResponse("Noto‘g‘ri viktorina tanlandi", status=400)

        # Savolni yaratamiz
        question = Question.objects.create(quiz=quiz, text=question_text)

        # Javoblarni qabul qilish (o'chirilgan satrlar tufayli indekslar orasida uzilishlar bo'lishi mumkin)
        indices = []
        for key in request.POST.keys():
            if key.startswith('answer_text_'):
                try:
                    idx = int(key.replace('answer_text_', ''))
                    indices.append(idx)
                except ValueError:
                    pass

        answers_to_create = []
        for idx in sorted(indices):
            answer_text = request.POST.get(f'answer_text_{idx}')
            is_correct = request.POST.get(f'is_correct_{idx}') == 'on'
            if answer_text:
                answers_to_create.append(
                    Answer(
                        question=question,
                        text=answer_text,
                        is_correct=is_correct
                    )
                )
        if answers_to_create:
            Answer.objects.bulk_create(answers_to_create)

        return redirect('question_list')

    # GET bo‘lsa — forma ko‘rsatamiz
    quizzes = Quiz.objects.all()
    return render(request, 'add-test-admin.html', {'quizzes': quizzes})


@subadmin_permission_required('manage_quizzes')
def question_list(request):
    questions = Question.objects.all()
    return render(request, 'admin-test-list.html', {'questions': questions})

@subadmin_permission_required('manage_quizzes')
@transaction.atomic
def update_question(request, question_id):
    question = get_object_or_404(Question, id=question_id)

    if request.method == "POST":
        # Savol matnini yangilash
        new_text = request.POST.get("question_text")
        if new_text:
            question.text = new_text

        # Quizni o‘zgartirish
        new_quiz_id = request.POST.get("quiz_id")
        if new_quiz_id:
            try:
                new_quiz = Quiz.objects.get(id=new_quiz_id)
                question.quiz = new_quiz
            except Quiz.DoesNotExist:
                pass  # noto‘g‘ri quiz id bo‘lsa, e’tiborsiz qoldiramiz

        question.save()

        # Eski javoblarni tahrirlash va o‘chirish
        for answer in question.answers.all():
            a_text = request.POST.get(f"answer_text_{answer.id}")
            is_correct = request.POST.get(f"is_correct_{answer.id}") == 'on'
            delete = request.POST.get(f"delete_answer_{answer.id}") == 'on'

            if delete:
                answer.delete()
            else:
                if a_text:
                    answer.text = a_text
                    answer.is_correct = is_correct
                    answer.save()

        # Yangi javoblar qo‘shish (indekslarni dinamik aniqlaymiz)
        new_indices = []
        for key in request.POST.keys():
            if key.startswith('new_answer_text_'):
                try:
                    idx = int(key.replace('new_answer_text_', ''))
                    new_indices.append(idx)
                except ValueError:
                    pass

        new_answers = []
        for idx in sorted(new_indices):
            text = request.POST.get(f"new_answer_text_{idx}")
            is_correct = request.POST.get(f"new_is_correct_{idx}") == 'on'
            if text:
                new_answers.append(
                    Answer(
                        question=question,
                        text=text,
                        is_correct=is_correct
                    )
                )
        if new_answers:
            Answer.objects.bulk_create(new_answers)

        return redirect('question_list')

    answers = question.answers.all()
    all_quizzes = Quiz.objects.all()

    return render(request, 'edit-test.html', {
        'question': question,
        'answers': answers,
        'all_quizzes': all_quizzes,
    })


@subadmin_permission_required('manage_quizzes')
def delete_question(request, pk):

    question = get_object_or_404(Question, pk=pk)

    if request.method == 'POST':
        question.delete()
        return redirect('question_list')  # o‘chirilgach qayta yuklash

    return HttpResponseForbidden("Noto‘g‘ri so‘rov")


@subadmin_permission_required('manage_quizzes')
def add_quiz(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        group_id = request.POST.get('group')
        teacher_id = request.POST.get('teacher')
        time_limit = request.POST.get('time_limit')
        max_score = request.POST.get('max_score')

        if not all([title, group_id, teacher_id, time_limit, max_score]):
            messages.error(request, "Iltimos, barcha maydonlarni to‘ldiring.")
        else:
            group = Group.objects.get(id=group_id)
            teacher = CustomUser.objects.get(id=teacher_id)

            Quiz.objects.create(
                title=title,
                group=group,
                teacher=teacher,
                time_limit=time_limit,
                max_score=max_score
            )
            messages.success(request, "Viktorina muvaffaqiyatli qo‘shildi.")
            return redirect('quiz_list')  # sahifani mos ravishda o‘zgartiring

    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')  # rolga qarab filtrlang

    return render(request, 'add-quiz-admin.html', {
        'groups': groups,
        'teachers': teachers,
    })


@subadmin_permission_required('manage_quizzes')
def quiz_list(request):

    quizzes = Quiz.objects.select_related('group', 'teacher').all().order_by('-created_at')
    return render(request, 'quiz-list-admin.html', {'quizzes': quizzes})


@subadmin_permission_required('manage_quizzes')
def edit_quiz(request, quiz_id):

    quiz = get_object_or_404(Quiz, id=quiz_id)
    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')

    if request.method == 'POST':
        quiz.title = request.POST.get('title')
        quiz.group_id = request.POST.get('group')
        quiz.teacher_id = request.POST.get('teacher')
        quiz.time_limit = request.POST.get('time_limit')
        quiz.max_score = request.POST.get('max_score')
        quiz.save()
        return redirect('quiz_list')

    return render(request, 'edit-quiz-admin.html', {
        'quiz': quiz,
        'groups': groups,
        'teachers': teachers,
    })

@subadmin_permission_required('manage_quizzes')
def delete_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.delete()
    messages.success(request, "Quiz muvaffaqiyatli o‘chirildi.")
    return redirect('quiz_list')


@admin_required
@transaction.atomic
def import_students_csv(request):
    import secrets

    # Sample CSV download handler
    if request.GET.get('download_sample'):
        role_type = request.GET.get('role', 'student')
        filename = f"{'o_quvchilar' if role_type == 'student' else 'o_qituvchilar'}_namuna.csv"
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')  # UTF-8 BOM for Excel compatibility

        writer = csv.writer(response)
        writer.writerow(['first_name', 'last_name', 'phone_number', 'username', 'password'])
        if role_type == 'student':
            writer.writerow(['Ali', 'Karimov', '+998901234567', '', ''])
            writer.writerow(['Vali', 'Rustamov', '+998931234568', 'vali_student', ''])
            writer.writerow(['Zuhra', 'Sobirova', '+998941234569', '', 'Parol1234'])
        else:
            writer.writerow(['Jasur', 'Abdullayev', '+998901234567', '', ''])
            writer.writerow(['Malika', 'Qosimova', '+998931234568', 't_malika', ''])
        return response

    imported_summary = request.session.get('last_imported_users', None)
    setting = SiteSetting.objects.first()

    if request.method == "POST":
        role = request.POST.get("role", "student")
        if role not in ['student', 'teacher']:
            messages.error(request, "Xavfsizlik xatosi: Faqat talaba yoki o'qituvchi import qilinishi mumkin!", extra_tags='import_error')
            return redirect("import_students_csv")

        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Iltimos, CSV fayl tanlang.", extra_tags='import_error')
            return redirect("import_students_csv")

        if not csv_file.name.endswith(".csv"):
            messages.error(request, "Faqat .csv fayl yuklashingiz mumkin!", extra_tags='import_error')
            return redirect("import_students_csv")

        send_sms_flag = request.POST.get("send_sms") == "on"

        try:
            data_set = csv_file.read().decode("utf-8-sig")
            io_string = io.StringIO(data_set)
            reader = csv.reader(io_string)

            raw_headers = next(reader, None)
            if not raw_headers:
                messages.error(request, "CSV fayl bo'sh!", extra_tags='import_error')
                return redirect("import_students_csv")

            headers = [h.strip().lower().replace(" ", "_") for h in raw_headers]

            # Flexible column mapping
            fn_idx = headers.index('first_name') if 'first_name' in headers else (headers.index('ism') if 'ism' in headers else (1 if len(headers) >= 2 else 0))
            ln_idx = headers.index('last_name') if 'last_name' in headers else (headers.index('familiya') if 'familiya' in headers else (2 if len(headers) >= 3 else 1))
            ph_idx = headers.index('phone_number') if 'phone_number' in headers else (headers.index('telefon') if 'telefon' in headers else (headers.index('phone') if 'phone' in headers else (3 if len(headers) >= 4 else 2)))
            un_idx = headers.index('username') if 'username' in headers else (headers.index('login') if 'login' in headers else (0 if 'username' in headers else None))
            pw_idx = headers.index('password') if 'password' in headers else (headers.index('parol') if 'parol' in headers else None)

            site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"
            site_url = request.build_absolute_uri('/')

            existing_usernames = set(CustomUser.objects.values_list('username', flat=True))
            imported_list = []
            created_count = 0
            sms_sent_count = 0

            for row_num, row in enumerate(reader, start=2):
                if not row or all(not cell.strip() for cell in row):
                    continue

                first_name = row[fn_idx].strip() if fn_idx < len(row) else ''
                last_name = row[ln_idx].strip() if ln_idx < len(row) else ''
                phone_raw = row[ph_idx].strip() if ph_idx < len(row) else ''

                if not (first_name or last_name) and not phone_raw:
                    continue

                phone_clean = clean_phone_number(phone_raw)

                # Username resolution
                username = row[un_idx].strip() if (un_idx is not None and un_idx < len(row)) else ''
                if not username:
                    phone_suffix = phone_clean[3:] if len(phone_clean) >= 12 else (phone_clean or str(secrets.randbelow(899999) + 100000))
                    username = f"{'std' if role == 'student' else 't'}_{phone_suffix}"

                orig_un = username
                c = 1
                while username in existing_usernames or CustomUser.objects.filter(username=username).exists():
                    username = f"{orig_un}_{c}"
                    c += 1

                # Password resolution (auto-generate if empty)
                raw_password = row[pw_idx].strip() if (pw_idx is not None and pw_idx < len(row)) else ''
                if not raw_password:
                    raw_password = generate_random_password(8)

                user = CustomUser.objects.create(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    phone_number=phone_raw or (f"+{phone_clean}" if phone_clean else ""),
                    role=role,
                    password=make_password(raw_password),
                    is_active=True
                )
                existing_usernames.add(username)
                created_count += 1

                # Send SMS if enabled & requested
                sms_status = "Yuborilmadi"
                if send_sms_flag and phone_clean and len(phone_clean) == 12:
                    sms_text = f"Assalomu alaykum, {first_name}! {site_name} tizimiga muvaffaqiyatli ro'yxatdan o'tdingiz.\nLogin: {username}\nParol: {raw_password}\nKirish: {site_url}"
                    sms_res = send_sms(phone_clean, sms_text, check_enabled=False)
                    if sms_res.get('success'):
                        sms_status = "Yuborildi"
                        sms_sent_count += 1
                    else:
                        sms_status = f"Xato: {sms_res.get('message')}"

                imported_list.append({
                    'name': f"{first_name} {last_name}".strip() or username,
                    'username': username,
                    'phone': phone_raw,
                    'password': raw_password,
                    'sms_status': sms_status
                })

            log_action(request.user, "CSV Import", f"{created_count} ta {role} CSV orqali import qilindi.", request)

            request.session['last_imported_users'] = {
                'count': created_count,
                'role': role,
                'sms_sent_count': sms_sent_count,
                'users': imported_list
            }

            messages.success(request, f"{created_count} ta {'o‘quvchi' if role == 'student' else 'o‘qituvchi'} muvaffaqiyatli import qilindi!", extra_tags='import_success')
        except Exception as e:
            messages.error(request, f"Importda xatolik: {str(e)}", extra_tags='import_error')

        return redirect("import_students_csv")

    return render(request, "import_students.html", {
        'setting': setting,
        'imported_summary': imported_summary
    })


@subadmin_permission_required('manage_payments')
def group_payment_list(request):
    groups = Group.objects.filter(payment_info__isnull=False).select_related("payment_info")
    return render(request, "group-payments-list.html", {"groups": groups})


@subadmin_permission_required('manage_payments')
def add_group_payment(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # Agar oldin mavjud bo'lsa
    payment_info = getattr(group, 'payment_info', None)

    if request.method == "POST":
        duration = request.POST.get('duration')
        monthly_fee = request.POST.get('monthly_fee')

        if payment_info:
            payment_info.course_duration_months = duration
            payment_info.monthly_fee = monthly_fee
            payment_info.save()
            messages.success(request, "To‘lov ma'lumotlari yangilandi.", extra_tags='payment_success')
        else:
            GroupPaymentInfo.objects.create(
                group=group,
                course_duration_months=duration,
                monthly_fee=monthly_fee
            )
            messages.success(request, "To‘lov ma'lumotlari qo‘shildi.", extra_tags='payment_success')

        return redirect('add_group_payment', group_id=group.id)

    return render(request, 'add_payment.html', {
        'group': group,
        'payment_info': payment_info
    })



# Guruhdagi o‘quvchilar ro‘yxati
@subadmin_permission_required('manage_payments')
def group_students(request, group_id):

    group = get_object_or_404(Group, id=group_id)
    students = group.students.all()
    months = [m[0] for m in StudentPayment.MONTH_CHOICES]
    return render(request, "admin_group_students.html", {"group": group, "students": students, "months": months,})

# O‘quvchi uchun to‘lov kiritish
@subadmin_permission_required('manage_payments')
def student_payment(request, group_id, student_id):

    group = get_object_or_404(Group, id=group_id)
    student = get_object_or_404(CustomUser, id=student_id, role="student")
    payment_info = get_object_or_404(GroupPaymentInfo, group=group)

    if request.method == "POST":
        month = request.POST.get("month")
        amount_paid = request.POST.get("amount_paid")
        pay_from_balance = request.POST.get("pay_from_balance") == '1'

        if not month or not amount_paid:
            messages.error(request, "Barcha maydonlarni to‘ldiring!", extra_tags='import_success')
            return redirect("student_payment", group_id=group.id, student_id=student.id)

        try:
            amount_paid_val = float(amount_paid)
        except ValueError:
            messages.error(request, "To'lov summasi noto'g'ri kiritildi.", extra_tags='import_success')
            return redirect("student_payment", group_id=group.id, student_id=student.id)

        if pay_from_balance:
            if student.balance < amount_paid_val:
                messages.error(request, "O'quvchi balansida yetarli mablag' mablag'lar mavjud emas!", extra_tags='import_success')
                return redirect("student_payment", group_id=group.id, student_id=student.id)

            with transaction.atomic():
                student.refresh_from_db()
                student.balance = F('balance') - amount_paid_val
                student.save()
                
                WalletTransaction.objects.create(
                    student=student,
                    amount=-amount_paid_val,
                    transaction_type='payment',
                    description=f"Guruh {group.name} uchun {month} oyi to'lovi hamyondan yechildi."
                )

        # To‘lov yozuvini yaratamiz va saqlaymiz
        payment = StudentPayment.objects.create(
            student=student,
            group=group,
            month=month,
            amount_paid=amount_paid_val,
        )
        log_action(request.user, "To'lov Kiritildi", f"{student.get_full_name()} uchun {group.name} guruhiga {month} oyi uchun {amount_paid_val} so'm to'lov kiritildi. (ID: {payment.id})", request)

        # PDF linkni yaratamiz
        pdf_url = reverse("payment_receipt", args=[payment.id])

        # Send Telegram notification if linked
        if student.telegram_chat_id:
            from main.telegram_service import send_telegram_message
            try:
                formatted_amount = f"{int(amount_paid):,}".replace(",", " ")
                receipt_url = request.build_absolute_uri(pdf_url)
                tg_text = (
                    f"<b>Yangi To'lov Qabul Qilindi</b> ✅\n\n"
                    f"<b>Talaba:</b> {student.first_name} {student.last_name}\n"
                    f"<b>Guruh:</b> {group.name}\n"
                    f"<b>Oy:</b> {payment.get_month_display()}\n"
                    f"<b>To'lov summasi:</b> {formatted_amount} so'm\n\n"
                    f"Sizning to'lovingiz tizimga muvaffaqiyatli kiritildi. Rahmat!\n"
                    f"📄 <a href='{receipt_url}'>To'lov chekini yuklab olish</a>"
                )
                send_telegram_message(student.telegram_chat_id, tg_text)
            except Exception as e:
                print(f"Failed to send payment telegram notification: {e}")

        student_name = escape(student.get_full_name() or student.username)
        messages.success(
            request,
            f"{student_name} uchun to‘lov saqlandi! "
            f"<a href='{pdf_url}' target='_blank' style='display: inline-block; padding: 6px 12px; margin-left: 10px; background: rgba(0, 242, 254, 0.15); border: 1px solid #00f2fe; color: #00f2fe; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; box-shadow: 0 0 10px rgba(0, 242, 254, 0.2); transition: 0.3s;'><i class=\"fas fa-file-pdf\"></i> PDF yuklab olish</a>",
            extra_tags='import_success'
        )

        return redirect("group_students", group_id=group.id)

    months = [m[0] for m in StudentPayment.MONTH_CHOICES]
    return render(request, "admin_group_students.html", {
        "group": group,
        "student": student,
        "payment_info": payment_info,
        "months": months
    })


@subadmin_permission_required('manage_students')
def student_list(request):
    students = CustomUser.objects.filter(role="student")
    return render(request, "admin_student_list.html", {"students": students})


@subadmin_permission_required('manage_payments')
def student_payment_history(request, student_id):
    student = get_object_or_404(CustomUser, id=student_id, role="student")
    payments = StudentPayment.objects.filter(student=student) \
        .select_related("group", "group__payment_info")

    # Oylarga tartib berish
    month_order = {month: idx for idx, (month, _) in enumerate(StudentPayment.MONTH_CHOICES)}

    payments = sorted(
        payments,
        key=lambda p: (p.group.name, month_order.get(p.month, 99))
    )

    # Guruh bo‘yicha to‘plab yuboramiz
    grouped_payments = []
    for group, group_items in groupby(payments, key=attrgetter("group")):
        grouped_payments.append({
            "group": group,
            "payments": list(group_items)
        })

    return render(request, "admin_student_payment_history.html", {
        "student": student,
        "grouped_payments": grouped_payments
    })
from PIL import Image, ImageDraw
def make_circle_image(image_path, size_px=100):
    img = Image.open(image_path).convert("RGBA")
    img = img.resize((size_px, size_px))

    mask = Image.new("L", (size_px, size_px), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size_px, size_px), fill=255)

    img.putalpha(mask)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


from reportlab.lib.units import mm
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import hashlib


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def payment_receipt(request, payment_id, bypass_auth=False):
    payment = get_object_or_404(StudentPayment, id=payment_id)

    if not bypass_auth:
        if not request.user.is_authenticated:
            return redirect('login')
        user = request.user
        is_owner = user.id == payment.student.id and user.role == 'student'
        is_admin = user.role == 'admin' or user.is_superuser or user.is_staff
        is_authorized_reception = user.role == 'reception' and isinstance(getattr(user, 'subadmin_permissions', None), list) and 'manage_payments' in user.subadmin_permissions
        if not (is_owner or is_admin or is_authorized_reception):
            return HttpResponseForbidden("Sizda ushbu chekni ko'rish huquqi yo'q!")

    # Tasdiqlash kodi
    unique_str = f"{payment.id}{payment.student.id}{payment.amount_paid}{payment.month}"
    verify_code = hashlib.sha256(unique_str.encode()).hexdigest()[:12]
    verify_url = request.build_absolute_uri(f"/payment/verify/{payment.id}/{verify_code}")

    # Local Wi-Fi tarmog'ida telefon ulanishi uchun 127.0.0.1/localhost o'rniga kompyuter IP manzilini qo'yamiz
    local_ip = get_local_ip()
    if "127.0.0.1" in verify_url:
        verify_url = verify_url.replace("127.0.0.1", local_ip)
    elif "localhost" in verify_url:
        verify_url = verify_url.replace("localhost", local_ip)

    # Kvitansiya raqami
    inv_number = f"INV-{payment.paid_at.year}-{payment.id:04d}"

    # PDF response
    response = HttpResponse(content_type='application/pdf')
    filename = f"chek_{payment.student.last_name}_{payment.month}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # 🖨️ Zamonaviy bank/terminal cheki o'lchami (Kengligi: 80mm, Bo'yi: 210mm)
    width = 80 * mm
    height = 210 * mm
    p = canvas.Canvas(response, pagesize=(width, height))

    # Orqa fonni toza oq qilish (Chop etishda bo'yoq iqtisodi uchun)
    p.setFillColor(colors.white)
    p.rect(0, 0, width, height, fill=True, stroke=False)

    # Dinamik boshlang'ich nuqta (Tepadan pastga qarab hisoblanadi)
    current_y = height - 12 * mm

    # 1. Tizim Logotipi (Mavjud bo'lsa markazga joylashadi)
    site_settings = SiteSetting.objects.first()
    if site_settings and site_settings.image:
        try:
            circle_img_buf = make_circle_image(site_settings.image.path, size_px=100)
            logo_img = ImageReader(circle_img_buf)
            p.drawImage(logo_img, (width / 2) - 10 * mm, current_y - 20 * mm, 20 * mm, 20 * mm, mask='auto')
            current_y -= 24 * mm
        except Exception:
            pass

    # 2. Chek Sarlavhasi (Kiberpank minimalizm)
    p.setFillColor(colors.HexColor("#070a12"))  # To'q brend rang
    p.setFont(FONT_BOLD, 12)
    site_name = site_settings.site_name if site_settings and site_settings.site_name else "Tizim"
    p.drawCentredString(width / 2, current_y, f"{site_name.upper()} TIZIMI")
    current_y -= 5 * mm

    p.setFont(FONT_NAME, 9)
    p.setFillColor(colors.HexColor("#4facfe"))  # Neon ko'k urgu
    p.drawCentredString(width / 2, current_y, "TO'LOV CHEKI")
    current_y -= 6 * mm

    # Yuqori ajratuvchi chiziq
    p.setStrokeColor(colors.HexColor("#e2e8f0"))
    p.setLineWidth(0.5)
    p.line(6 * mm, current_y, width - 6 * mm, current_y)
    current_y -= 6 * mm

    # 3. Strukturaviy Ma'lumotlar (Kalit so'zlar chapda, qiymatlar o'ngda)
    data = [
        ["Chek raqami:", inv_number],
        ["O'quvchi:", f"{payment.student.first_name} {payment.student.last_name}"],
        ["Guruh:", payment.group.name],
        ["Oy uchun:", payment.month],
        ["Kurs narxi:", f"{payment.group.payment_info.monthly_fee:,.0f} so'm"],
        ["To'langan summa:", f"{payment.amount_paid:,.0f} so'm"],
        ["To'lov vaqti:", timezone.localtime(payment.paid_at).strftime("%d.%m.%Y %H:%M")],
    ]

    table = Table(data, colWidths=[31 * mm, 37 * mm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#1e293b")),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),

        # To'langan summa satrini vizual ajratish (Yashil neon effekt)
        ('FONTNAME', (0, 5), (1, 5), FONT_BOLD),
        ('TEXTCOLOR', (0, 5), (1, 5), colors.HexColor("#00aa6c")),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor("#f1f5f9")),
    ]))

    # Jadval balandligini dinamik hisoblab chekni surish
    tw, th = table.wrap(width - 12 * mm, height)
    current_y -= th
    table.drawOn(p, 6 * mm, current_y)
    current_y -= 6 * mm

    # Pastki ajratuvchi chiziq
    p.line(6 * mm, current_y, width - 6 * mm, current_y)
    current_y -= 8 * mm

    # 4. Markazlashtirilgan QR Kod
    qr_img = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_image = ImageReader(qr_buffer)

    qr_size = 28 * mm
    current_y -= qr_size
    p.drawImage(qr_image, (width / 2) - (qr_size / 2), current_y, qr_size, qr_size)
    current_y -= 5 * mm

    # QR kod ostidagi kichik ma'lumot matni
    p.setFont(FONT_NAME, 7)
    p.setFillColor(colors.HexColor("#64748b"))
    p.drawCentredString(width / 2, current_y, "Chekni haqiqiyligini tekshirish uchun")
    current_y -= 3 * mm
    p.drawCentredString(width / 2, current_y, "QR-kodni skaner qiling.")
    current_y -= 12 * mm

    # 5. Terminal yakuniy terminal matni
    p.setFont(FONT_BOLD, 8)
    p.setFillColor(colors.HexColor("#070a12"))
    p.drawCentredString(width / 2, current_y, "TO'LOV TASDIQLANGAN")

    p.showPage()
    p.save()
    return response

def verify_payment(request, payment_id, code):
    try:
        payment = StudentPayment.objects.get(id=payment_id)
    except StudentPayment.DoesNotExist:
        return HttpResponse("Bu hujjat bazada mavjud emas")

    # QR kod tekshirish
    unique_str = f"{payment.id}{payment.student.id}{payment.amount_paid}{payment.month}"
    real_code = hashlib.sha256(unique_str.encode()).hexdigest()[:12]

    if code == real_code:
        # PDF kvitansiyani qaytarish
        return payment_receipt(request, payment.id, bypass_auth=True)
    else:
        return HttpResponse("Bu hujjat bazada mavjud emas")


@login_required
def student_payment_pdf(request, student_id):
    user = request.user
    is_authorized_reception = user.role == 'reception' and isinstance(getattr(user, 'subadmin_permissions', None), list) and 'manage_payments' in user.subadmin_permissions
    if not (user.is_superuser or user.is_staff or user.role == 'admin' or is_authorized_reception or user.id == student_id):
        return HttpResponseForbidden("Sizda ushbu amalni bajarish uchun ruxsat yo'q!")

    # O'quvchini bazadan olish
    student = get_object_or_404(CustomUser, id=student_id, role='student')

    # O'quvchining barcha to'lovlari
    payments = StudentPayment.objects.filter(student=student).select_related("group__payment_info").order_by("paid_at")

    # Jami moliyaviy ko'rsatkichlarni hisoblash
    total_paid = sum(p.amount_paid for p in payments)
    payment_count = payments.count()

    # Superuser yoki admin rolidagilardan birortasini ismli variantini qidirish
    admin_user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(role='admin').first()

    if admin_user and (admin_user.first_name or admin_user.last_name):
        admin_name = f"{admin_user.first_name} {admin_user.last_name}"
    else:
        admin_name = "Tizim Administratori"

    # HTTP javobni PDF sifatida rasmiylashtirish
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reyestr_{student.last_name}_payments.pdf"'

    # Rasmiy A4 moliya hujjati andozasi (Chekkalar: 15mm)
    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )
    elements = []
    styles = getSampleStyleSheet()

    # --- 🏢 PROFESSIONAL MOLIYAVIY STILLAR ---
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=FONT_BOLD,
        fontSize=20,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        fontName=FONT_BOLD,
        fontSize=8.5,
        textColor=colors.HexColor("#4facfe"),
        spaceAfter=15
    )
    meta_label = ParagraphStyle(
        'MetaLabel',
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
        leading=14
    )
    meta_value = ParagraphStyle(
        'MetaValue',
        fontName=FONT_NAME,
        fontSize=9,
        textColor=colors.HexColor("#0f172a"),
        leading=14
    )
    card_label = ParagraphStyle(
        'CardLabel',
        fontName=FONT_BOLD,
        fontSize=9.5,
        textColor=colors.HexColor("#4facfe")
    )
    card_value = ParagraphStyle(
        'CardValue',
        fontName=FONT_BOLD,
        fontSize=15,
        textColor=colors.HexColor("#0f172a")
    )
    th_style = ParagraphStyle(
        'TableHeader',
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=colors.white,
        alignment=1
    )
    td_style = ParagraphStyle(
        'TableCell',
        fontName=FONT_NAME,
        fontSize=9,
        textColor=colors.HexColor("#334155"),
        alignment=1,
        leading=14
    )

    # 1. IKKI TOMONLAMA HEADER PANEL
    left_header = [
        [Paragraph("MOLIYAVIY TO'LOVLAR REYESTRI", title_style)],
        [Paragraph("STATEMENT OF ACCOUNT / AUDIT REPORT", subtitle_style)]
    ]
    left_table = Table(left_header, colWidths=[105 * mm])
    left_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))

    right_meta = [
        [Paragraph("O'quvchi:", meta_label), Paragraph(f"{student.first_name} {student.last_name}", meta_value)],
        [Paragraph("Talaba ID:", meta_label), Paragraph(f"#{student.id}", meta_value)],
        [Paragraph("Yaratildi:", meta_label), Paragraph(timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M"), meta_value)]
    ]
    right_table = Table(right_meta, colWidths=[20 * mm, 55 * mm])
    right_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    header_grid = Table([[left_table, right_table]], colWidths=[105 * mm, 75 * mm])
    header_grid.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(header_grid)

    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f172a"), spaceAfter=15))

    # 2. STATISTIKA VA BALANCE KARTALARI BLOKI
    stats_data = [
        [Paragraph("JAMI SHAKLLANTIRILGAN MABLAG'", card_label), Paragraph("MUVAFFAQIYATLI TO'LOVLAR", card_label)],
        [Paragraph(f"{total_paid:,.0f} so'm", card_value), Paragraph(f"{payment_count} ta tranzaksiya", card_value)]
    ]
    stats_table = Table(stats_data, colWidths=[105 * mm, 75 * mm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 20))

    # 3. MOLIYAVIY REYESTR JADVALI (Kengliklar: 180mm)
    col_widths = [45 * mm, 23 * mm, 25 * mm, 27 * mm, 28 * mm, 32 * mm]

    data = [[
        Paragraph("Guruh nomi", th_style),
        Paragraph("Hisob oyi", th_style),
        Paragraph("Davomiyligi", th_style),
        Paragraph("Kurs narxi", th_style),
        Paragraph("To'langan", th_style),
        Paragraph("Tranzaksiya vaqti", th_style)
    ]]

    for p in payments:
        try:
            group_info = p.group.payment_info
            course_duration = f"{group_info.course_duration_months} oy"
            monthly_fee = f"{group_info.monthly_fee:,.0f} so'm"
        except GroupPaymentInfo.DoesNotExist:
            course_duration = "-"
            monthly_fee = "-"

        data.append([
            Paragraph(p.group.name, td_style),
            Paragraph(p.month, td_style),
            Paragraph(course_duration, td_style),
            Paragraph(monthly_fee, td_style),
            Paragraph(f"{p.amount_paid:,.0f} so'm",
                      ParagraphStyle('GText', parent=td_style, textColor=colors.HexColor("#00aa6c"),
                                     fontName=FONT_BOLD)),
            Paragraph(timezone.localtime(p.paid_at).strftime("%d.%m.%Y %H:%M"), td_style),
        ])

    main_table = Table(data, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 35))

    # 4. 🛡️ IMZOLAR VA AKADEMIYA LOGOTIPI ASOSIDAGI RASMIY MUHR BLOKI
    # Muhr qutisi uchun default qiymat tayyorlash
    stamp_element = Paragraph("[ Rasmiy muhr o'rni ]",
                              ParagraphStyle('NoStamp', parent=td_style, textColor=colors.HexColor("#94a3b8")))

    site_settings = SiteSetting.objects.first()
    if site_settings and site_settings.image:
        try:
            # Dumaloq kiber muhr buferini generatsiya qilamiz
            circle_img_buf = make_circle_image(site_settings.image.path, size_px=120)
            # ReportLab oqim ob'ektiga o'tkazamiz (Hajmi: 26x26 mm)
            stamp_element = RLImage(circle_img_buf, width=26 * mm, height=26 * mm)
        except Exception:
            pass

    footer_data = [
        [
            Paragraph(f"<b>Bosh hisobchi:</b><br/>{admin_name}<br/><br/><br/>Imzo: ___________________", td_style),
            Paragraph(f"<b>Moliya bo'limi boshlig'i:</b><br/>{admin_name}<br/><br/><br/>Imzo: ___________________",
                      td_style),
            stamp_element
        ]
    ]

    footer_table = Table(footer_data, colWidths=[65 * mm, 65 * mm, 50 * mm])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(footer_table)

    # PDF hisobotni yakuniy yig'ish
    doc.build(elements)
    return response


from main.models import SystemAnnouncement

@subadmin_permission_required('manage_announcements')
def announcement_list(request):

    announcements = SystemAnnouncement.objects.all().order_by('-created_at')
    return render(request, 'announcement_list.html', {
        'announcements': announcements
    })

@subadmin_permission_required('manage_announcements')
def create_announcement(request):

    if request.method == 'POST':
        title = request.POST.get('title')
        message = request.POST.get('message')
        target_role = request.POST.get('target_role')
        category = request.POST.get('category')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        is_active = request.POST.get('is_active') == 'on'

        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
        
        st = parse_datetime(start_time)
        et = parse_datetime(end_time)
        
        if st and timezone.is_naive(st):
            st = timezone.make_aware(st)
        if et and timezone.is_naive(et):
            et = timezone.make_aware(et)

        if not title or not message or not et:
            messages.error(request, "Iltimos, barcha zarur maydonlarni to'ldiring.")
        else:
            SystemAnnouncement.objects.create(
                title=title,
                message=message,
                target_role=target_role,
                category=category,
                start_time=st or timezone.now(),
                end_time=et,
                is_active=is_active
            )
            messages.success(request, "Tizim xabari muvaffaqiyatli yaratildi.")
            return redirect('announcement_list')

    return render(request, 'announcement_form.html', {
        'title_text': "Yangi xabar yuborish",
        'button_text': "Yuborish"
    })

@subadmin_permission_required('manage_announcements')
def edit_announcement(request, announcement_id):

    announcement = get_object_or_404(SystemAnnouncement, id=announcement_id)

    if request.method == 'POST':
        title = request.POST.get('title')
        message = request.POST.get('message')
        target_role = request.POST.get('target_role')
        category = request.POST.get('category')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        is_active = request.POST.get('is_active') == 'on'

        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
        
        st = parse_datetime(start_time)
        et = parse_datetime(end_time)
        
        if st and timezone.is_naive(st):
            st = timezone.make_aware(st)
        if et and timezone.is_naive(et):
            et = timezone.make_aware(et)

        if not title or not message or not et:
            messages.error(request, "Iltimos, barcha zarur maydonlarni to'ldiring.")
        else:
            announcement.title = title
            announcement.message = message
            announcement.target_role = target_role
            announcement.category = category
            announcement.start_time = st or timezone.now()
            announcement.end_time = et
            announcement.is_active = is_active
            announcement.save()
            messages.success(request, "Tizim xabari yangilandi.")
            return redirect('announcement_list')

    st_iso = timezone.localtime(announcement.start_time).strftime('%Y-%m-%dT%H:%M') if announcement.start_time else ""
    et_iso = timezone.localtime(announcement.end_time).strftime('%Y-%m-%dT%H:%M') if announcement.end_time else ""

    return render(request, 'announcement_form.html', {
        'announcement': announcement,
        'st_iso': st_iso,
        'et_iso': et_iso,
        'title_text': "Xabarni tahrirlash",
        'button_text': "Saqlash"
    })

@admin_required
def delete_announcement(request, announcement_id):

    announcement = get_object_or_404(SystemAnnouncement, id=announcement_id)
    announcement.delete()
    messages.success(request, "Tizim xabari muvaffaqiyatli o'chirildi.")
    return redirect('announcement_list')


import csv
import urllib.parse
from django.db.models import Sum

@subadmin_permission_required('manage_payments')
def debtors_list(request):

    MONTH_MAPPING = {
        1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
        5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
        9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
    }
    
    current_month_num = timezone.now().month
    default_month = MONTH_MAPPING.get(current_month_num, "Yanvar")
    
    selected_month = request.GET.get('month', default_month)
    selected_group_id = request.GET.get('group', 'all')
    
    groups = Group.objects.select_related('payment_info').all()
    
    if selected_group_id != 'all':
        groups_to_check = groups.filter(id=selected_group_id)
    else:
        groups_to_check = groups

    debtors = []

    for group in groups_to_check:
        if not hasattr(group, 'payment_info'):
            continue
        
        monthly_fee = group.payment_info.monthly_fee
        if monthly_fee <= 0:
            continue
        
        students = group.students.all()
        
        for student in students:
            total_paid = StudentPayment.objects.filter(
                student=student,
                group=group,
                month=selected_month
            ).aggregate(total=Sum('amount_paid'))['total'] or 0
            
            if total_paid < monthly_fee:
                debt_amount = monthly_fee - total_paid
                student_name = f"{student.first_name} {student.last_name}" if (student.first_name or student.last_name) else student.username
                
                # Pre-filled telegram message text
                msg = f"Salom! Hurmatli {student_name}, {group.name} guruhi uchun {selected_month} oyi to'lovidan {int(debt_amount):,} so'm qarzdorligingiz mavjud. Iltimos, to'lovni tez orada amalga oshiring. Rahmat!"
                tg_share_url = f"https://t.me/share/url?text={urllib.parse.quote(msg)}"
                
                debtors.append({
                    'student': student,
                    'student_name': student_name,
                    'group': group,
                    'monthly_fee': monthly_fee,
                    'total_paid': total_paid,
                    'debt_amount': debt_amount,
                    'telegram_url': tg_share_url,
                    'raw_message': msg,
                })
                
    debtors.sort(key=lambda x: x['debt_amount'], reverse=True)
    months = [m for m in MONTH_MAPPING.values()]

    return render(request, 'debtors_list.html', {
        'debtors': debtors,
        'groups': groups,
        'months': months,
        'selected_month': selected_month,
        'selected_group_id': selected_group_id,
    })


@subadmin_permission_required('manage_payments')
def export_debtors_csv(request):

    MONTH_MAPPING = {
        1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
        5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
        9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
    }
    
    current_month_num = timezone.now().month
    default_month = MONTH_MAPPING.get(current_month_num, "Yanvar")
    
    selected_month = request.GET.get('month', default_month)
    selected_group_id = request.GET.get('group', 'all')
    
    groups = Group.objects.select_related('payment_info').all()
    if selected_group_id != 'all':
        groups_to_check = groups.filter(id=selected_group_id)
    else:
        groups_to_check = groups

    import tablib
    headers = [
        "O'quvchi", 
        "Telefon raqami", 
        "Guruh", 
        "To'lov oyi", 
        "Kurs narxi (so'm)", 
        "To'lagan (so'm)", 
        "Qarz miqdori (so'm)"
    ]
    data = tablib.Dataset(headers=headers)

    for group in groups_to_check:
        if not hasattr(group, 'payment_info'):
            continue
        monthly_fee = group.payment_info.monthly_fee
        if monthly_fee <= 0:
            continue
        
        students = group.students.all()
        for student in students:
            total_paid = StudentPayment.objects.filter(
                student=student,
                group=group,
                month=selected_month
            ).aggregate(total=Sum('amount_paid'))['total'] or 0
            
            if total_paid < monthly_fee:
                debt_amount = monthly_fee - total_paid
                student_name = f"{student.first_name} {student.last_name}" if (student.first_name or student.last_name) else student.username
                data.append([
                    student_name,
                    student.phone_number,
                    group.name,
                    selected_month,
                    float(monthly_fee),
                    float(total_paid),
                    float(debt_amount)
                ])

    response = HttpResponse(
        data.export('xlsx'),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="qarzdorlar_{selected_month}.xlsx"'
    return response


@subadmin_permission_required('manage_payments')
def export_payments_csv(request):

    query = request.GET.get('query', '').strip()
    payments = StudentPayment.objects.select_related('student', 'group').order_by('-paid_at')
    
    if query:
        payments = payments.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(group__name__icontains=query) |
            Q(month__icontains=query)
        )

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="to_lovlar_tarixi.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        "To'lov ID", 
        "O'quvchi ismi", 
        "Telefon raqami", 
        "Guruh", 
        "To'lov oyi", 
        "To'langan summa (so'm)", 
        "Sana"
    ])

    for payment in payments:
        writer.writerow([
            payment.id,
            f"{payment.student.first_name} {payment.student.last_name}" if (payment.student.first_name or payment.student.last_name) else payment.student.username,
            payment.student.phone_number,
            payment.group.name,
            payment.month,
            float(payment.amount_paid),
            timezone.localtime(payment.paid_at).strftime('%d.%m.%Y %H:%M')
        ])

    return response


@subadmin_permission_required('manage_attendance')
def admin_attendance_overview(request):

    groups = Group.objects.all().prefetch_related('students')
    
    # 1. Tezkor guruhlar statistikasi (1 ta agregat so'rov orqali)
    group_agg = Attendance.objects.values('group_id').annotate(
        total=Count('id'),
        present=Count('id', filter=Q(status='present')),
        dates_count=Count('date', distinct=True)
    )
    group_agg_map = {item['group_id']: item for item in group_agg}

    group_stats = []
    for group in groups:
        agg = group_agg_map.get(group.id, {})
        total_records = agg.get('total', 0)
        total_present = agg.get('present', 0)
        avg_attendance = (total_present / total_records * 100) if total_records > 0 else 100
        dates_count = agg.get('dates_count', 0)
        
        group_stats.append({
            'group': group,
            'students_count': group.students.count(),
            'total_classes': dates_count,
            'avg_attendance': round(avg_attendance, 1)
        })

    # 2. Chronic absent tracker (Tahlil) - 1 ta so'rov orqali xotirada tahlil qilish
    records_by_gs = {}
    for r in Attendance.objects.values('group_id', 'student_id', 'status').order_by('date'):
        key = (r['group_id'], r['student_id'])
        if key not in records_by_gs:
            records_by_gs[key] = []
        records_by_gs[key].append(r['status'])

    chronic_absentees = []
    for group in groups:
        for student in group.students.all():
            statuses = records_by_gs.get((group.id, student.id), [])
            total_classes = len(statuses)
            if total_classes < 3:
                continue

            present_classes = statuses.count('present')
            absent_classes = statuses.count('absent')
            rate = (present_classes / total_classes * 100) if total_classes > 0 else 100

            # Ketma-ket kelmagan darslar soni (oxirgisidan boshlab)
            consecutive_absences = 0
            for s in reversed(statuses):
                if s == 'absent':
                    consecutive_absences += 1
                else:
                    break

            if rate < 70 or consecutive_absences >= 3:
                msg_text = f"Salom! Hurmatli {student.first_name} {student.last_name}, sizning {group.name} guruhidagi darslarda ishtirokingiz pastligi aniqlandi (Davomatingiz: {round(rate, 0)}%). "
                if consecutive_absences >= 3:
                    msg_text += f"Siz oxirgi ketma-ket {consecutive_absences} ta darsda qatnashmadingiz. "
                msg_text += "Iltimos, dars qoldirish sababini ma'lum qiling yoki o'quv markazi bilan bog'laning."
                
                telegram_url = f"https://t.me/share/url?url=&text={urllib.parse.quote(msg_text)}"

                chronic_absentees.append({
                    'student': student,
                    'group': group,
                    'total_classes': total_classes,
                    'absent_classes': absent_classes,
                    'rate': round(rate, 1),
                    'consecutive_absences': consecutive_absences,
                    'telegram_url': telegram_url,
                    'raw_message': msg_text
                })

    return render(request, 'admin_attendance_overview.html', {
        'group_stats': group_stats,
        'chronic_absentees': chronic_absentees,
    })


@subadmin_permission_required('manage_attendance')
def admin_group_attendance(request, group_id):

    group = get_object_or_404(Group, id=group_id)
    students = group.students.all()
    
    range_val = request.GET.get('range', '7')
    
    # Guruhning barcha unikal sanalarini olamiz
    all_dates = sorted(set(Attendance.objects.filter(group=group).values_list('date', flat=True)))
    total_dates_count = len(all_dates)

    today = timezone.localdate()
    if range_val == '7':
        start_date = today - timedelta(days=7)
        filtered_dates = [d for d in all_dates if d >= start_date]
        if not filtered_dates and all_dates:
            filtered_dates = all_dates[-7:]
    elif range_val == '30':
        start_date = today - timedelta(days=30)
        filtered_dates = [d for d in all_dates if d >= start_date]
        if not filtered_dates and all_dates:
            filtered_dates = all_dates[-15:]
    elif range_val == '60':
        start_date = today - timedelta(days=60)
        filtered_dates = [d for d in all_dates if d >= start_date]
        if not filtered_dates and all_dates:
            filtered_dates = all_dates[-30:]
    else:
        filtered_dates = all_dates
        range_val = 'all'

    # Faqat kerakli sanalardagi davomatlarni bitta so'rovda olamiz
    attendances = Attendance.objects.filter(group=group, date__in=filtered_dates)

    # N+1 so'rovlarni oldini olish uchun xotirada xaritalash: (student_id, date) -> (status, id)
    att_map = {(a.student_id, a.date): (a.status, a.id) for a in attendances}

    attendance_list = []
    for student in students:
        student_dates = []
        for d in filtered_dates:
            status, att_id = att_map.get((student.id, d), (None, None))
            student_dates.append({
                'date': d,
                'status': status,
                'id': att_id
            })
        attendance_list.append({
            'student': student,
            'dates': student_dates
        })

    return render(request, 'admin_group_attendance.html', {
        'group': group,
        'dates': filtered_dates,
        'attendance_list': attendance_list,
        'range_val': range_val,
        'total_dates_count': total_dates_count,
    })


@subadmin_permission_required('manage_attendance')
def admin_update_attendance_ajax(request):
    user = request.user
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            student_id = data.get('student_id')
            group_id = data.get('group_id')
            date_str = data.get('date')
            new_status = data.get('status')

            if new_status not in ['present', 'absent']:
                return JsonResponse({'success': False, 'error': 'Noto\'g\'ri status'}, status=400)

            from datetime import datetime
            d = datetime.strptime(date_str, '%Y-%m-%d').date()

            record, created = Attendance.objects.get_or_create(
                student_id=student_id,
                group_id=group_id,
                date=d,
                defaults={
                    'status': new_status,
                    'teacher': user
                }
            )

            if not created:
                record.status = new_status
                record.save()

            # Send Telegram warning if marked as absent
            if new_status == 'absent':
                try:
                    student = record.student
                    if student.telegram_chat_id:
                        from main.telegram_service import send_telegram_message
                        formatted_date = d.strftime('%d.%m.%Y')
                        tg_text = (
                            f"<b>Davomat haqida ogohlantirish</b> ⚠️\n\n"
                            f"Salom, {student.first_name} {student.last_name}!\n"
                            f"Siz <b>{formatted_date}</b> kuni <b>{record.group.name}</b> guruhidagi darsga kelmadingiz (darsda ishtirok etmadingiz).\n\n"
                            f"Iltimos, o'quv jarayonini o'z vaqtida o'zlashtiring va darslarni sababsiz qoldirmang."
                        )
                        send_telegram_message(student.telegram_chat_id, tg_text)
                except Exception as e:
                    print(f"Failed to send attendance telegram notification: {e}")

            return JsonResponse({'success': True, 'new_status': new_status, 'record_id': record.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Faqat POST so\'rovi'}, status=405)



@subadmin_permission_required('manage_media')
def admin_media_gallery(request):
    user = request.user
    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')
    videos = GroupVideo.objects.select_related('group', 'teacher').order_by('-created_at')

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        group_id = request.POST.get('group_id')
        teacher_id = request.POST.get('teacher_id')
        video_file = request.FILES.get('video_file')
        youtube_link = request.POST.get('youtube_link')

        if not title or not group_id:
            messages.error(request, "Sarlavha va Guruh tanlanishi majburiy!")
            return redirect('admin_media_gallery')

        if not video_file and not youtube_link:
            messages.error(request, "Iltimos, video fayl yuklang yoki YouTube havola kiriting!")
            return redirect('admin_media_gallery')

        if video_file:
            from main.validators import check_file_upload, validate_video_file
            is_valid, err_msg = check_file_upload(video_file, validate_video_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('admin_media_gallery')

        group = get_object_or_404(Group, id=group_id)
        
        teacher = None
        if teacher_id:
            teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')

        GroupVideo.objects.create(
            title=title,
            description=description,
            group=group,
            teacher=teacher,
            video_file=video_file,
            youtube_link=youtube_link
        )
        messages.success(request, "Video dars muvaffaqiyatli yuklandi!", extra_tags='video_toast')
        return redirect('admin_media_gallery')

    return render(request, 'admin_media_gallery.html', {
        'admin': user,
        'groups': groups,
        'teachers': teachers,
        'videos': videos
    })


@subadmin_permission_required('manage_media')
def admin_edit_video(request, video_id):

    video = get_object_or_404(GroupVideo, id=video_id)

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        group_id = request.POST.get('group_id')
        teacher_id = request.POST.get('teacher_id')
        video_file = request.FILES.get('video_file')
        youtube_link = request.POST.get('youtube_link')

        if video_file:
            from main.validators import check_file_upload, validate_video_file
            is_valid, err_msg = check_file_upload(video_file, validate_video_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('admin_media_gallery')

        if title:
            video.title = title
        video.description = description
        if youtube_link is not None:
            video.youtube_link = youtube_link
        if group_id:
            video.group = get_object_or_404(Group, id=group_id)
        
        if teacher_id:
            video.teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')
        else:
            video.teacher = None

        if video_file:
            video.video_file = video_file

        video.save()
        messages.success(request, "Video dars muvaffaqiyatli yangilandi!", extra_tags='video_toast')
    return redirect('admin_media_gallery')


@subadmin_permission_required('manage_media')
def admin_delete_video(request, video_id):

    video = get_object_or_404(GroupVideo, id=video_id)
    video.delete()
    messages.success(request, "Video dars muvaffaqiyatli o'chirildi!", extra_tags='video_toast')
    return redirect('admin_media_gallery')


@subadmin_permission_required('manage_quizzes')
def admin_quiz_results(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    group = quiz.group
    memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
    results = StudentQuizResult.objects.filter(quiz=quiz).select_related('student')
    result_map = {result.student.id: result for result in results}
    students_data = []
    total_questions = quiz.questions.count()
    for membership in memberships:
        student = membership.student
        if membership.joined_at > quiz.created_at:
            continue
        result = result_map.get(student.id)
        if result:
            correct_count = round(result.score / quiz.max_score * total_questions) if quiz.max_score > 0 else 0
        else:
            correct_count = None
        students_data.append({'student': student, 'result': result, 'correct_count': correct_count, 'total_questions': total_questions})
    return render(request, 'admin_quiz_results.html', {'quiz': quiz, 'students_data': students_data})


@subadmin_permission_required('manage_assignments')
def admin_assignment_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    group = assignment.group
    memberships = GroupStudentMembership.objects.filter(group=group, joined_at__lte=assignment.created_at).select_related('student')
    submissions = AssignmentSubmission.objects.filter(assignment=assignment)
    submissions_dict = {s.student_id: s for s in submissions}
    student_data = []
    for membership in memberships:
        student = membership.student
        submission = submissions_dict.get(student.id)
        student_data.append({'student': student, 'submission': submission})
    return render(request, 'admin_assignment_submissions.html', {'assignment': assignment, 'student_data': student_data})


@subadmin_permission_required('manage_assignments')
def admin_grade_assignment(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        assignment_id = request.POST.get('assignment_id')
        score = request.POST.get('score')
        submission = get_object_or_404(AssignmentSubmission, student_id=student_id, assignment_id=assignment_id)
        submission.grade = int(score)
        submission.save()
        messages.success(request, 'O\'quvchi topshirig\'i muvaffaqiyatli baholandi!')
        return redirect('admin_assignment_submissions', assignment_id=assignment_id)
    return redirect('admin_assignment_list')


@admin_required
def admin_settings_view(request):

    setting = SiteSetting.objects.first()
    profile = ProfileSetting.objects.first()

    if request.method == 'POST':
        logo = request.FILES.get('logo')
        default_profile = request.FILES.get('default_profile')
        site_name = request.POST.get('site_name')

        if site_name is not None:
            site_name = site_name.strip()
            if site_name:
                if not setting:
                    setting = SiteSetting.objects.create(site_name=site_name)
                else:
                    setting.site_name = site_name
                    setting.save()
                messages.success(request, "Brend nomi muvaffaqiyatli o'zgartirildi.")

        if logo:
            from main.validators import check_file_upload, validate_image_file
            is_valid, err_msg = check_file_upload(logo, validate_image_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('admin_settings')
            if not setting:
                setting = SiteSetting.objects.create(image=logo)
            else:
                setting.image = logo
                setting.save()
            messages.success(request, "Tizim logotipi muvaffaqiyatli o'zgartirildi.")

        if default_profile:
            from main.validators import check_file_upload, validate_image_file
            is_valid, err_msg = check_file_upload(default_profile, validate_image_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('admin_settings')
            if not profile:
                profile = ProfileSetting.objects.create(image=default_profile)
            else:
                profile.image = default_profile
                profile.save()
            messages.success(request, "Standart profil rasmi muvaffaqiyatli o'zgartirildi.")

        login_bg_image = request.FILES.get('login_bg_image')
        if login_bg_image:
            from main.validators import check_file_upload, validate_image_file
            is_valid, err_msg = check_file_upload(login_bg_image, validate_image_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('admin_settings')
            if not setting:
                setting = SiteSetting.objects.create(login_bg_image=login_bg_image)
            else:
                setting.login_bg_image = login_bg_image
                setting.save()
            messages.success(request, "Login sahifasi fon rasmi muvaffaqiyatli o'zgartirildi.")

        # Eskiz.uz SMS Settings Form handling
        if 'eskiz_settings_form' in request.POST or 'eskiz_email' in request.POST:
            if not setting:
                setting = SiteSetting.objects.create()
            
            eskiz_email = request.POST.get('eskiz_email')
            if eskiz_email is not None:
                setting.eskiz_email = eskiz_email.strip()

            eskiz_password = request.POST.get('eskiz_password')
            if eskiz_password is not None and eskiz_password.strip():
                setting.eskiz_password = eskiz_password.strip()

            eskiz_from_name = request.POST.get('eskiz_from_name')
            if eskiz_from_name is not None:
                setting.eskiz_from_name = eskiz_from_name.strip() or "4546"

            setting.sms_enabled = request.POST.get('sms_enabled') == 'on'
            setting.sms_on_register = request.POST.get('sms_on_register') == 'on'
            setting.sms_on_payment = request.POST.get('sms_on_payment') == 'on'
            setting.sms_on_absence = request.POST.get('sms_on_absence') == 'on'
            setting.save()

            from django.core.cache import cache
            cache.delete("eskiz_api_bearer_token")
            messages.success(request, "Eskiz.uz SMS sozlamalari muvaffaqiyatli saqlandi.")

        from django.core.cache import cache
        cache.delete('site_global_images')
        return redirect('admin_settings')

    sub_admins = CustomUser.objects.filter(role='reception').order_by('-joined_at')
    return render(request, 'admin_settings.html', {
        'setting': setting,
        'profile': profile,
        'sub_admins': sub_admins,
    })


def add_subadmin(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        permissions = request.POST.getlist('permissions')

        if not (username and password and first_name and last_name and phone_number):
            messages.error(request, "Iltimos, barcha maydonlarni to'ldiring.")
            return redirect('admin_settings')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f"'{username}' foydalanuvchi nomi tizimda mavjud.")
            return redirect('admin_settings')

        try:
            user = CustomUser.objects.create(
                username=username,
                password=make_password(password),
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                role='reception',
                subadmin_permissions=permissions
            )
            messages.success(request, f"Yangi sub-admin ({first_name} {last_name}) muvaffaqiyatli yaratildi.")
        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return redirect('admin_settings')


@admin_required
def edit_subadmin(request, subadmin_id):
    sub_admin = get_object_or_404(CustomUser, id=subadmin_id, role='reception')
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        permissions = request.POST.getlist('permissions')

        if not (first_name and last_name and phone_number):
            messages.error(request, "Ism, Familiya va Telefon raqami majburiy.")
            return redirect('admin_settings')

        try:
            sub_admin.first_name = first_name
            sub_admin.last_name = last_name
            sub_admin.phone_number = phone_number
            sub_admin.subadmin_permissions = permissions

            if password:
                sub_admin.password = make_password(password)

            sub_admin.save()
            messages.success(request, f"Sub-admin ({first_name} {last_name}) ma'lumotlari muvaffaqiyatli yangilandi.")
        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")

    return redirect('admin_settings')


@admin_required
def delete_subadmin(request, subadmin_id):
    sub_admin = get_object_or_404(CustomUser, id=subadmin_id, role='reception')
    if request.method == 'POST':
        try:
            name = f"{sub_admin.first_name} {sub_admin.last_name}"
            sub_admin.delete()
            messages.success(request, f"Sub-admin ({name}) muvaffaqiyatli o'chirildi.")
        except Exception as e:
            messages.error(request, f"Xatolik yuz berdi: {str(e)}")
    return redirect('admin_settings')


@admin_required
def admin_sessions_view(request):

    sessions = UserSession.objects.select_related('user').order_by('-last_activity')
    return render(request, 'admin_sessions.html', {
        'sessions': sessions
    })


@admin_required
@require_http_methods(["POST"])
@transaction.atomic
def terminate_session_view(request, session_key):
    from django.contrib.sessions.models import Session
    # Django sessiyalaridan o'chirish
    Session.objects.filter(session_key=session_key).delete()
    # UserSession modelida nofaol qilish yoki o'chirish
    UserSession.objects.filter(session_key=session_key).delete()

    messages.success(request, "Foydalanuvchi seansi muvaffaqiyatli yakunlandi (tizimdan chiqarildi).")
    return redirect('admin_sessions')



@admin_required
def admin_audit_logs(request):

    logs = AuditLog.objects.select_related('user').order_by('-timestamp')

    query = request.GET.get('query', '')
    if query:
        logs = logs.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(action__icontains=query) |
            Q(description__icontains=query)
        )

    selected_role = request.GET.get('role', 'all')
    if selected_role == 'admin':
        logs = logs.filter(user__role='admin')
    elif selected_role == 'subadmin':
        logs = logs.filter(user__role='reception')
    elif selected_role == 'teacher':
        logs = logs.filter(user__role='teacher')
    elif selected_role == 'student':
        logs = logs.filter(user__role='student')
    elif selected_role == 'system':
        logs = logs.filter(user__isnull=True)

    return render(request, 'admin_audit_logs.html', {
        'logs': logs[:500],  # limit to 500 logs for performance
        'query': query,
        'selected_role': selected_role
    })


@role_required(['admin', 'reception'])
def admin_financial_stats_api(request):

    all_months = StudentPayment.objects.values_list('month', flat=True).distinct()
    available_years = set()
    for m in all_months:
        parts = m.split()
        if len(parts) == 2 and parts[1].isdigit():
            available_years.add(int(parts[1]))
    
    available_years = sorted(list(available_years), reverse=True)
    if not available_years:
        available_years = [timezone.now().year]

    selected_year = request.GET.get('year')
    if selected_year and selected_year.isdigit():
        selected_year = int(selected_year)
    else:
        selected_year = available_years[0]

    MONTH_NAMES = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
    year_suffix = f" {selected_year}"

    # Filter payments for the selected year once
    payments_this_year = StudentPayment.objects.filter(month__endswith=year_suffix)

    # 1. Aggregate monthly payments in a single query
    monthly_totals = payments_this_year.values('month').annotate(total=Sum('amount_paid'))
    monthly_totals_map = {item['month']: item['total'] for item in monthly_totals}

    monthly_revenue = []
    for month_name in MONTH_NAMES:
        month_query = f"{month_name}{year_suffix}"
        total = monthly_totals_map.get(month_query) or 0
        monthly_revenue.append({
            'month': month_name,
            'total': float(total)
        })

    # 2. Aggregate payments by group in a single query
    group_payments = []
    group_totals = payments_this_year.values('group_id', 'group__name').annotate(total=Sum('amount_paid'))
    for item in group_totals:
        total = item['total'] or 0
        if total > 0:
            group_payments.append({
                'group_name': item['group__name'] or f"Guruh #{item['group_id']}",
                'total': float(total)
            })

    return JsonResponse({
        'monthly_revenue': monthly_revenue,
        'group_payments': group_payments,
        'available_years': available_years,
        'selected_year': selected_year
    })


@subadmin_permission_required('manage_payments')
def get_student_discount(request, group_id, student_id, month):

    group = get_object_or_404(Group, id=group_id)
    student = get_object_or_404(CustomUser, id=student_id, role="student")

    MONTH_NAMES = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
    MONTH_NUMBERS = {name: idx + 1 for idx, name in enumerate(MONTH_NAMES)}

    if month not in MONTH_NUMBERS:
        return JsonResponse({'error': 'Noto\'g\'ri oy'}, status=400)

    current_month_num = MONTH_NUMBERS[month]

    if current_month_num == 1:
        prev_month_num = 12
    else:
        prev_month_num = current_month_num - 1

    # Davomatni tekshiramiz
    attendance_qs = Attendance.objects.filter(student=student, group=group, date__month=prev_month_num)
    total_att = attendance_qs.count()
    present_att = attendance_qs.filter(status='present').count()
    attendance_rate = (present_att / total_att) if total_att > 0 else 1.0

    # Akademik natijalar (testlar va topshiriqlar)
    quizzes = Quiz.objects.filter(group=group, created_at__month=prev_month_num)
    assignments = Assignment.objects.filter(group=group, created_at__month=prev_month_num)

    quiz_results = StudentQuizResult.objects.filter(student=student, quiz__in=quizzes)
    submissions = AssignmentSubmission.objects.filter(student=student, assignment__in=assignments, grade__isnull=False)

    scores = []

    for q in quizzes:
        res = quiz_results.filter(quiz=q).first()
        if res:
            pct = (res.score / q.max_score * 100) if q.max_score > 0 else 0
            scores.append(pct)
        else:
            scores.append(0)

    for a in assignments:
        sub = submissions.filter(assignment=a).first()
        if sub:
            pct = (sub.grade / a.max_score * 100) if a.max_score > 0 else 0
            scores.append(pct)
        else:
            scores.append(0)

    avg_academic_score = sum(scores) / len(scores) if scores else 100.0

    discount_percent = 0
    badge_name = "Nishon yo'q"
    badge_color = "#64748b"
    reason = "Imtiyoz mavjud emas"

    attendance_pct = round(attendance_rate * 100)
    academic_pct = round(avg_academic_score)

    # Agar o'quv faolligi yoki davomati yozilgan bo'lsagina chegirma hisoblaymiz
    if total_att > 0 or scores:
        if attendance_rate == 1.0 and avg_academic_score >= 95.0:
            discount_percent = 100
            badge_name = "Oltin Nishon"
            badge_color = "#ffb000"
            reason = f"O'tgan oyda davomat 100% va o'rtacha ball {academic_pct}% bo'lgani uchun"
        elif attendance_rate >= 0.95 and avg_academic_score >= 85.0:
            discount_percent = 50
            badge_name = "Kumush Nishon"
            badge_color = "#00f2fe"
            reason = f"O'tgan oyda davomat {attendance_pct}% va o'rtacha ball {academic_pct}% bo'lgani uchun"
        elif attendance_rate >= 0.90 and avg_academic_score >= 75.0:
            discount_percent = 10
            badge_name = "Bronza Nishon"
            badge_color = "#ff9f43"
            reason = f"O'tgan oyda davomat {attendance_pct}% va o'rtacha ball {academic_pct}% bo'lgani uchun"
        else:
            reason = f"Ko'rsatkichlar yetarli emas (Davomat: {attendance_pct}%, O'rtacha ball: {academic_pct}%)"
    else:
        reason = "O'tgan oyda hech qanday o'quv faoliyati yoki davomat yozilmagan"

    monthly_fee = 0
    try:
        payment_info = group.payment_info
        monthly_fee = float(payment_info.monthly_fee)
    except GroupPaymentInfo.DoesNotExist:
        pass

    discount_amount = monthly_fee * (discount_percent / 100)
    final_amount = monthly_fee - discount_amount

    return JsonResponse({
        'discount_percent': discount_percent,
        'discount_amount': discount_amount,
        'final_amount': final_amount,
        'badge_name': badge_name,
        'badge_color': badge_color,
        'reason': reason
    })


# ==========================================
# 📊 DTM MOCK IMTIHON & AI OMR VIEWS
# ==========================================
import json
import random
import string
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from pydantic import BaseModel
from typing import List, Dict
from google import genai
from google.genai import types
from PIL import Image as PILImage
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak, NextPageTemplate
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from main.models import DTMExam, DTMQuestionPool, DTMAnswerPool, DTMRegistration, StudentDTMExamResult


class ParsedQuestion(BaseModel):
    text: str
    options: List[str]
    correct_option_index: int  # 1-indexed (1, 2, 3, 4)


class ParsedExam(BaseModel):
    questions: List[ParsedQuestion]


class OMRScannedResult(BaseModel):
    booklet_number: str
    answers: Dict[str, str]  # e.g. {"1": "A", "2": "B"}


class BookletQuestionInput(BaseModel):
    number: int
    text: str
    options: List[str]


class BookletExamInput(BaseModel):
    questions: List[BookletQuestionInput]



@subadmin_permission_required('manage_dtm')
def admin_dtm_list(request):

    from django.db.models import Count, Q
    
    # 📈 Savollar bazasi statistikasi
    total_questions = DTMQuestionPool.objects.count()
    stats_raw = DTMQuestionPool.objects.values('subject').annotate(
        total=Count('id'),
        compulsory=Count('id', filter=Q(is_compulsory=True)),
        block=Count('id', filter=Q(is_compulsory=False)),
        easy=Count('id', filter=Q(difficulty=3)),
        medium=Count('id', filter=Q(difficulty=2)),
        hard=Count('id', filter=Q(difficulty=1)),
    ).order_by('subject')

    exams = DTMExam.objects.all().order_by('-exam_date')
    return render(request, 'admin_dtm_list.html', {
        'exams': exams,
        'total_questions': total_questions,
        'stats': stats_raw
    })


@subadmin_permission_required('manage_dtm')
def admin_dtm_create(request):

    if request.method == 'POST':
        title = request.POST.get('title')
        reg_deadline = parse_datetime(request.POST.get('registration_deadline'))
        exam_date = parse_datetime(request.POST.get('exam_date'))
        
        b1_count = int(request.POST.get('block1_questions_count', 30))
        b1_score = float(request.POST.get('block1_score', 3.1))
        b2_count = int(request.POST.get('block2_questions_count', 30))
        b2_score = float(request.POST.get('block2_score', 2.1))
        
        comp_count = int(request.POST.get('compulsory_questions_count', 10))
        comp_score = float(request.POST.get('compulsory_score', 1.1))

        if title and reg_deadline and exam_date:
            DTMExam.objects.create(
                title=title,
                registration_deadline=reg_deadline,
                exam_date=exam_date,
                block1_questions_count=b1_count,
                block1_score=b1_score,
                block2_questions_count=b2_count,
                block2_score=b2_score,
                compulsory_questions_count=comp_count,
                compulsory_score=comp_score
            )
            messages.success(request, "DTM Imtihoni muvaffaqiyatli yaratildi va o'quvchilarga yuborildi!")
            return redirect('admin_dtm_list')
        else:
            messages.error(request, "Barcha majburiy maydonlarni to'ldiring!")

    return render(request, 'admin_dtm_create.html')


@subadmin_permission_required('manage_dtm')
def admin_dtm_edit(request, exam_id):

    exam = get_object_or_404(DTMExam, id=exam_id)

    if request.method == 'POST':
        title = request.POST.get('title')
        reg_deadline = parse_datetime(request.POST.get('registration_deadline'))
        exam_date = parse_datetime(request.POST.get('exam_date'))
        
        b1_count = int(request.POST.get('block1_questions_count', 30))
        b1_score = float(request.POST.get('block1_score', 3.1))
        b2_count = int(request.POST.get('block2_questions_count', 30))
        b2_score = float(request.POST.get('block2_score', 2.1))
        
        comp_count = int(request.POST.get('compulsory_questions_count', 10))
        comp_score = float(request.POST.get('compulsory_score', 1.1))
        
        is_active = request.POST.get('is_active') == 'on'

        if title and reg_deadline and exam_date:
            exam.title = title
            exam.registration_deadline = reg_deadline
            exam.exam_date = exam_date
            exam.block1_questions_count = b1_count
            exam.block1_score = b1_score
            exam.block2_questions_count = b2_count
            exam.block2_score = b2_score
            exam.compulsory_questions_count = comp_count
            exam.compulsory_score = comp_score
            exam.is_active = is_active
            exam.save()
            
            messages.success(request, f"{exam.title} imtihoni muvaffaqiyatli tahrirlandi!")
            return redirect('admin_dtm_list')
        else:
            messages.error(request, "Barcha majburiy maydonlarni to'ldiring!")

    return render(request, 'admin_dtm_edit.html', {
        'exam': exam
    })


def extract_images_from_docx(file_path, target_dir, prefix):
    import docx
    from docx.oxml.ns import qn
    import os
    
    doc = docx.Document(file_path)
    os.makedirs(target_dir, exist_ok=True)
    
    paragraphs_text = []
    image_counter = 1
    image_mapping = {}
    
    def process_paragraph(p):
        nonlocal image_counter
        p_text = p.text
        for run in p.runs:
            rElem = run._r
            drawings = rElem.xpath('.//w:drawing')
            if drawings:
                for drawing in drawings:
                    blips = drawing.xpath('.//a:blip')
                    for blip in blips:
                        embed_id = blip.get(qn('r:embed'))
                        if embed_id and embed_id in doc.part.related_parts:
                            part = doc.part.related_parts[embed_id]
                            try:
                                img_data = part.blob
                                ext = os.path.splitext(part.partname)[1] or '.png'
                                filename = f"img_{prefix}_{image_counter}{ext}"
                                filepath = os.path.join(target_dir, filename)
                                with open(filepath, 'wb') as f:
                                    f.write(img_data)
                                
                                p_text += f" [DIAGRAM_IMAGE_{image_counter}]"
                                image_mapping[str(image_counter)] = filename
                                image_counter += 1
                            except Exception:
                                pass
        return p_text

    for p in doc.paragraphs:
        paragraphs_text.append(process_paragraph(p))
        
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    paragraphs_text.append(process_paragraph(p))
        
    return "\n".join(paragraphs_text), image_mapping



def extract_images_from_pdf(file_path, target_dir, prefix):
    import pypdf
    import os
    
    reader = pypdf.PdfReader(file_path)
    os.makedirs(target_dir, exist_ok=True)
    
    pages_text = []
    image_counter = 1
    image_mapping = {}
    
    for page in reader.pages:
        page_text = page.extract_text() or ""
        
        try:
            if '/Resources' in page and '/XObject' in page['/Resources']:
                xObject = page['/Resources']['/XObject'].get_object()
                for obj in xObject:
                    if xObject[obj]['/Subtype'] == '/Image':
                        data = xObject[obj].get_data()
                        ext = ".png"
                        filename = f"img_{prefix}_{image_counter}{ext}"
                        filepath = os.path.join(target_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(data)
                        
                        page_text += f" [DIAGRAM_IMAGE_{image_counter}]"
                        image_mapping[str(image_counter)] = filename
                        image_counter += 1
        except Exception:
            pass
            
        pages_text.append(page_text)
        
    return "\n".join(pages_text), image_mapping


@subadmin_permission_required('manage_dtm')
@transaction.atomic
def admin_dtm_manual_bulk_add(request):
    subjects = ["Matematika", "Fizika", "Kimyo", "Biologiya", "Ingliz tili", "Ona tili", "Tarix", "Geografiya"]

    if request.method == 'POST':
        subject = request.POST.get('subject')
        difficulty = int(request.POST.get('difficulty', 2))
        is_compulsory = request.POST.get('is_compulsory') == 'on'
        
        try:
            q_count = int(request.POST.get('question_count', 0))
        except ValueError:
            q_count = 0
            
        import uuid
        import os
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        
        saved_questions = 0
        for i in range(1, q_count + 1):
            q_text = request.POST.get(f'q_text_{i}')
            if not q_text or not q_text.strip():
                continue
                
            uploaded_image = request.FILES.get(f'q_image_{i}')
            image_filename = ""
            if uploaded_image:
                ext = os.path.splitext(uploaded_image.name)[1] or '.png'
                image_filename = f"img_manual_{uuid.uuid4().hex[:12]}{ext}"
                default_storage.save(f"dtm_images/{image_filename}", ContentFile(uploaded_image.read()))
                q_text += f" [DIAGRAM_IMAGE:{image_filename}]"
                
            question = DTMQuestionPool.objects.create(
                subject=subject,
                difficulty=difficulty,
                is_compulsory=is_compulsory,
                text=q_text
            )
            
            correct_idx = int(request.POST.get(f'q_correct_{i}', 1)) - 1
            
            answers_to_create = []
            for opt_idx in range(4):
                opt_num = opt_idx + 1
                opt_text = request.POST.get(f'q_opt_{i}_{opt_num}', '')
                
                # Check for uploaded image for this option
                uploaded_opt_image = request.FILES.get(f'q_image_{i}_{opt_num}')
                if uploaded_opt_image:
                    ext = os.path.splitext(uploaded_opt_image.name)[1] or '.png'
                    opt_image_filename = f"img_manual_opt_{uuid.uuid4().hex[:12]}{ext}"
                    default_storage.save(f"dtm_images/{opt_image_filename}", ContentFile(uploaded_opt_image.read()))
                    opt_text += f" [DIAGRAM_IMAGE:{opt_image_filename}]"
                
                is_corr = (opt_idx == correct_idx)
                answers_to_create.append(
                    DTMAnswerPool(
                        question=question,
                        text=opt_text,
                        is_correct=is_corr
                    )
                )
            if answers_to_create:
                DTMAnswerPool.objects.bulk_create(answers_to_create)
            saved_questions += 1
            
        if saved_questions > 0:
            messages.success(request, f"{saved_questions} ta savol muvaffaqiyatli bazaga saqlandi.")
        else:
            messages.warning(request, "Hech qanday savol kiritilmadi.")
        return redirect('admin_dtm_questions_list')


    return render(request, 'admin_dtm_manual_bulk_add.html', {
        'subjects': subjects,
    })


@subadmin_permission_required('manage_dtm')
def admin_dtm_registrations(request, exam_id):

    exam = get_object_or_404(DTMExam, id=exam_id)
    registrations = DTMRegistration.objects.filter(exam=exam).select_related('student', 'result')
    return render(request, 'admin_dtm_registrations.html', {
        'exam': exam,
        'registrations': registrations
    })


import hashlib
import urllib.parse
import requests
import re
from PIL import Image as PILImage

def fetch_latex_img_path(latex_code):
    cache_dir = os.path.join(settings.MEDIA_ROOT, 'latex_cache')
    os.makedirs(cache_dir, exist_ok=True)
    latex_hash = hashlib.md5(latex_code.encode('utf-8')).hexdigest()
    filename = f"latex_{latex_hash}.png"
    file_path = os.path.join(cache_dir, filename)
    
    if not os.path.exists(file_path):
        rendered = False
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            formula = latex_code.strip()
            if formula.startswith('$$') and formula.endswith('$$'):
                formula = formula[2:-2].strip()
            elif formula.startswith('$') and formula.endswith('$'):
                formula = formula[1:-1].strip()
            formula = f"${formula}$"
            
            fig = plt.figure(figsize=(0.1, 0.1))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')
            ax.text(0.5, 0.5, formula, fontsize=12, ha='center', va='center', color='black', math_fontfamily='cm')
            
            plt.savefig(file_path, dpi=200, bbox_inches='tight', pad_inches=0.02, transparent=False, facecolor='white')
            plt.close(fig)
            rendered = True
        except Exception as local_err:
            print(f"Local matplotlib LaTeX rendering failed for '{latex_code}': {local_err}. Falling back to CodeCogs.")
            
        if not rendered:
            try:
                encoded_latex = urllib.parse.quote(latex_code)
                url = f"https://latex.codecogs.com/png.image?\\dpi{{130}}\\bg{{white}}{encoded_latex}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                else:
                    return None
            except Exception as e:
                print(f"Error downloading LaTeX image: {e}")
                return None
                
    if os.path.exists(file_path):
        try:
            with PILImage.open(file_path) as img:
                return file_path, img.size[0], img.size[1]
        except Exception:
            pass
    return None

def fetch_latex_img(latex_code, is_display=False):
    img_info = fetch_latex_img_path(latex_code)
    if not img_info:
        return None
    file_path, w, h = img_info
    w_points = int(w * 0.55)
    h_points = int(h * 0.55)
    
    if not is_display:
        if h_points > 30:
            w_points = int(w_points * (30 / h_points))
            h_points = 30
        return f'<img src="{file_path}" width="{w_points}" height="{h_points}" valign="middle"/>'
    else:
        if w_points > 220:
            h_points = int(h_points * (220 / w_points))
            w_points = 220
        return f'<br/><br/><img src="{file_path}" width="{w_points}" height="{h_points}"/><br/><br/>'

def clean_option_text(text):
    if not text:
        return ""
    # Strip leading A), B), C), D) or A., B., C., D. (case-insensitive)
    cleaned = re.sub(r'^\s*[A-D]\s*[\)\.\-]\s*', '', text, flags=re.IGNORECASE)
    return cleaned.strip()


def restore_html_tags(escaped_text):
    if not escaped_text:
        return ""
    escaped_text = escaped_text.replace('&lt;sub&gt;', '<sub>').replace('&lt;/sub&gt;', '</sub>')
    escaped_text = escaped_text.replace('&lt;sup&gt;', '<sup>').replace('&lt;/sup&gt;', '</sup>')
    escaped_text = escaped_text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    escaped_text = escaped_text.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    return escaped_text

def text_to_flowables(text, style, number_prefix=""):
    from django.utils.html import escape
    escaped = escape(text)
    escaped = restore_html_tags(escaped)
    
    def replace_inline(match):
        latex_code = match.group(1).strip()
        img_tag = fetch_latex_img(latex_code, is_display=False)
        return img_tag if img_tag else match.group(0)
    
    display_matches = []
    def hide_display(match):
        display_matches.append(match.group(1).strip())
        return f"__DISPLAY_MATH_PLACEHOLDER_{len(display_matches)-1}__"
    
    temp_text = re.sub(r'\$\$(.*?)\$\$', hide_display, escaped)
    temp_text = re.sub(r'\$(.*?)\$', replace_inline, temp_text)
    
    pattern = re.compile(r'(\[DIAGRAM_IMAGE:[^\]]+\]|__DISPLAY_MATH_PLACEHOLDER_\d+__)')
    parts = pattern.split(temp_text)
    
    flowables = []
    first_paragraph = True
    
    for part in parts:
        if not part:
            continue
            
        if part.startswith('[DIAGRAM_IMAGE:'):
            filename = part[15:-1].strip()
            from reportlab.platypus import Image as RLImage
            full_path = os.path.join(settings.MEDIA_ROOT, 'dtm_images', filename)
            if os.path.exists(full_path):
                try:
                    with PILImage.open(full_path) as img:
                        w, h = img.size
                        max_w = 200
                        if w > max_w:
                            h = int(h * (max_w / w))
                            w = max_w
                        rl_img = RLImage(full_path, width=w, height=h)
                        rl_img.hAlign = 'CENTER'
                        flowables.append(Spacer(1, 4))
                        flowables.append(rl_img)
                        flowables.append(Spacer(1, 4))
                except Exception as e:
                    print(f"Error loading diagram in flowable: {e}")
        elif part.startswith('__DISPLAY_MATH_PLACEHOLDER_'):
            idx = int(part[27:-2])
            latex_code = display_matches[idx]
            img_info = fetch_latex_img_path(latex_code)
            if img_info:
                file_path, w, h = img_info
                from reportlab.platypus import Image as RLImage
                w_points = int(w * 0.55)
                h_points = int(h * 0.55)
                if w_points > 220:
                    h_points = int(h_points * (220 / w_points))
                    w_points = 220
                rl_img = RLImage(file_path, width=w_points, height=h_points)
                rl_img.hAlign = 'CENTER'
                flowables.append(Spacer(1, 4))
                flowables.append(rl_img)
                flowables.append(Spacer(1, 4))
        else:
            if first_paragraph and number_prefix:
                para_text = f"{number_prefix} {part}"
                first_paragraph = False
            else:
                para_text = part
                
            if para_text.strip():
                style.leading = max(style.fontSize + 4, style.leading)
                flowables.append(Paragraph(para_text, style))
                
    return flowables


@subadmin_permission_required('manage_dtm')
def admin_dtm_generate_booklet(request, registration_id):

    registration = get_object_or_404(DTMRegistration, id=registration_id)
    exam = registration.exam

    # Random kitobcha raqami generatsiya qilish (7 xonali)
    while True:
        booklet_num = "".join(random.choices(string.digits, k=7))
        if not DTMRegistration.objects.filter(booklet_number=booklet_num).exists():
            break

    registration.booklet_number = booklet_num

    # 1. Savollarni guruhlash va tanlash
    answers_key = {}      # OMR tekshirish uchun unikal kalit mapping: {"1": {"q_id": x, "correct": "A"}}

    # Savollarni tanlash yordamchi logikasi
    def pick_questions(subject, count, is_compulsory):
        q_ids = list(DTMQuestionPool.objects.filter(subject=subject, is_compulsory=is_compulsory).values_list('id', flat=True))
        if len(q_ids) <= count:
            return list(DTMQuestionPool.objects.filter(id__in=q_ids).prefetch_related('answers'))
        sampled_ids = random.sample(q_ids, count)
        return list(DTMQuestionPool.objects.filter(id__in=sampled_ids).prefetch_related('answers'))

    # Blok 1 va Blok 2 savollari
    b1_questions = pick_questions(registration.block1_subject, exam.block1_questions_count, False)
    b2_questions = pick_questions(registration.block2_subject, exam.block2_questions_count, False)

    # DTM ga mos ravishda raw_sections tuzish
    raw_sections = []
    if registration.take_compulsory:
        # Majburiy fanlar sarlavhasi
        raw_sections.append(("MAJBURIY FANLAR", []))
        
        # Majburiy fanlar qismlari (Ona tili, Matematika, O'zbekiston tarixi)
        m_ona_tili = pick_questions("Ona tili", exam.compulsory_questions_count, True)
        if m_ona_tili:
            raw_sections.append(("ONA TILI", m_ona_tili))
        m_matem = pick_questions("Matematika", exam.compulsory_questions_count, True)
        if m_matem:
            raw_sections.append(("MATEMATIKA", m_matem))
        m_tarix = pick_questions("Tarix", exam.compulsory_questions_count, True)
        if m_tarix:
            raw_sections.append(("O'ZBEKISTON TARIXI", m_tarix))
    
    # Mutaxassislik fanlari sarlavhalari
    raw_sections.append((registration.block1_subject.upper(), b1_questions))
    raw_sections.append((registration.block2_subject.upper(), b2_questions))

    global_q_index = 1
    pdf_content_sections = []

    for title, q_list in raw_sections:
        # Sarlavhani qo'shamiz
        pdf_content_sections.append({'type': 'header', 'text': title})
        
        # Agar savollar mavjud bo'lsa, ularni qo'shamiz
        for q in q_list:
            answers = list(q.answers.all())
            random.shuffle(answers)  # Variantlarni aralashtirish
            
            raw_options = [ans.text for ans in answers]
            correct_idx = 0
            for a_idx, ans in enumerate(answers):
                if ans.is_correct:
                    correct_idx = a_idx
                    break
            
            correct_letter = chr(65 + correct_idx)  # A, B, C, D

            answers_key[str(global_q_index)] = {
                'question_id': q.id,
                'correct_letter': correct_letter
            }

            pdf_content_sections.append({
                'type': 'question',
                'number': global_q_index,
                'text': q.text,
                'options': raw_options
            })
            global_q_index += 1

    # Kalitni saqlaymiz
    registration.booklet_answers_key = json.dumps(answers_key)

    # 1.5 Savollarni AI orqali tozalash va formatlash (Gemini 2.5 Flash)
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            questions_to_clean = []
            for item in pdf_content_sections:
                if item['type'] == 'question':
                    questions_to_clean.append({
                        'number': item['number'],
                        'text': item['text'],
                        'options': item['options']
                    })
            
            if questions_to_clean:
                prompt = """
                Siz DTM imtihon kitobchalarini nashrga tayyorlovchi professional redaktorsiz.
                Sizga berilgan savollar va variantlar ro'yxatini imlo, grammatika, matematik va fizikaviy formulalar dizayni jihatidan ideal holatga keltiring:
                1. Matematik va fizikaviy formulalarni har doim toza LaTeX/KaTeX formatida yozing.
                2. Satr ichidagi formulalarni $...$ belgilari bilan o'rang (masalan: $x^2 = y^3$, $\alpha$, $\vec{p}$, $\sqrt{x}$).
                3. Blokli/alohida qatordagi yirik formulalarni $$...$$ belgilari bilan o'rang (masalan: $$\frac{a}{b}$$).
                4. [DIAGRAM_IMAGE:...] ko'rinishidagi rasm belgilarini aslo o'zgartirmang, ularni matndagi o'z joyida qoldiring.
                5. Variantlar matnlariga hech qanday A), B), C), D) kabi harf prefikslarini qo'shmang, ularni faqat toza matn yoki formula sifatida formatlang.
                6. Variantlar tartibini aslo o'zgartirmang.
                7. Imlo xatolarini tuzating, lekin ilmiy atamalar va savol mazmunini o'zgartirmang.
                """
                
                client = genai.Client(api_key=api_key)
                input_data = json.dumps({'questions': questions_to_clean}, ensure_ascii=False)
                
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=[prompt + f"\n\nSavollar:\n{input_data}"],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BookletExamInput,
                        temperature=0.1,
                        max_output_tokens=8192
                    )
                )
                
                cleaned_data = json.loads(response.text)
                cleaned_questions = cleaned_data.get('questions', [])
                cleaned_map = {q['number']: q for q in cleaned_questions}
                
                for item in pdf_content_sections:
                    if item['type'] == 'question' and item['number'] in cleaned_map:
                        cleaned_item = cleaned_map[item['number']]
                        item['text'] = cleaned_item.get('text', item['text'])
                        cleaned_opts = cleaned_item.get('options', [])
                        if len(cleaned_opts) == len(item['options']):
                            item['options'] = cleaned_opts
                            
        except Exception as gemini_err:
            print(f"Booklet Gemini Formatting failed: {str(gemini_err)}")

    # 2. ReportLab PDF Kitobcha generatsiya qilish
    import io
    from django.core.files.base import ContentFile
    from reportlab.graphics.shapes import Drawing, Rect, Circle, String
    from reportlab.platypus import KeepTogether, BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak, NextPageTemplate
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from django.utils.html import escape

    buffer = io.BytesIO()

    # Base Document template with 1-column Cover and 2-column Body
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    
    # Booklet number metadata
    booklet_num_str = booklet_num
    tip_code = booklet_num_str[-3:]

    # Page decorations callback for body pages
    def draw_body_page_decorations(canvas, document):
        canvas.saveState()
        
        # Header layout
        header_text_left = f"T-{tip_code}"
        header_text_center = f"Test topshiriqlari kitobi ({booklet_num_str})"
        
        canvas.setFont(FONT_BOLD, 10)
        canvas.drawString(36, 808, header_text_left)
        
        canvas.setFont(FONT_ITALIC, 9)
        canvas.drawCentredString(297.5, 808, header_text_center)
        
        # Solid line under header
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(1.5)
        canvas.line(36, 800, 559, 800)
        
        # Vertical dividing line between columns
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(1)
        canvas.line(297.5, 36, 297.5, 785)
        
        # Centered page number
        canvas.setFont(FONT_NAME, 9)
        canvas.setFillColor(colors.black)
        canvas.drawCentredString(297.5, 20, str(document.page))
        
        canvas.restoreState()

    # Frames definition
    frame_cover = Frame(36, 36, 523, 770, id='cover_frame', topPadding=20, bottomPadding=20)
    
    # Left and right frames (height 740, starts at 36, so top is 776)
    frame_left = Frame(36, 36, 248, 740, id='col1', topPadding=0, bottomPadding=0, leftPadding=0, rightPadding=0)
    frame_right = Frame(311, 36, 248, 740, id='col2', topPadding=0, bottomPadding=0, leftPadding=0, rightPadding=0)

    # Templates
    template_cover = PageTemplate(id='Cover', frames=frame_cover)
    template_body = PageTemplate(id='TwoCols', frames=[frame_left, frame_right], onPage=draw_body_page_decorations)
    doc.addPageTemplates([template_cover, template_body])

    styles = getSampleStyleSheet()
    
    # Custom styles
    section_header_style = ParagraphStyle(
        'SecHeader', parent=styles['Normal'], fontName=FONT_BOLD, fontSize=11, leading=13,
        textColor=colors.black, alignment=1, spaceBefore=12, spaceAfter=8, keepWithNext=True
    )
    question_style = ParagraphStyle(
        'QuestionText', parent=styles['Normal'], fontName=FONT_NAME, fontSize=8.5, leading=11,
        textColor=colors.black, spaceBefore=6, spaceAfter=4, keepWithNext=True
    )
    option_style = ParagraphStyle(
        'OptionText', parent=styles['Normal'], fontName=FONT_NAME, fontSize=8.5, leading=11,
        textColor=colors.black, leftIndent=12, spaceAfter=1.5
    )

    story = []

    # Cover Page Elements
    # 1. Top right code "32-17"
    story.append(Paragraph("32-17", ParagraphStyle('TopRightCode', fontName=FONT_NAME, fontSize=9, alignment=2, spaceAfter=5)))

    # 2. Mock QR code Marker Drawing
    qr_drawing = Drawing(30, 30)
    qr_drawing.add(Rect(0, 0, 30, 30, fillColor=colors.black, strokeColor=colors.black))
    qr_drawing.add(Rect(3, 3, 8, 8, fillColor=colors.white, strokeColor=colors.white))
    qr_drawing.add(Rect(19, 3, 8, 8, fillColor=colors.white, strokeColor=colors.white))
    qr_drawing.add(Rect(3, 19, 8, 8, fillColor=colors.white, strokeColor=colors.white))
    qr_drawing.add(Rect(5, 5, 4, 4, fillColor=colors.black, strokeColor=colors.black))
    qr_drawing.add(Rect(21, 5, 4, 4, fillColor=colors.black, strokeColor=colors.black))
    qr_drawing.add(Rect(5, 21, 4, 4, fillColor=colors.black, strokeColor=colors.black))

    # 3. Top booklet info box
    top_box_data = [
        [
            qr_drawing,
            Paragraph(f"KITOB RAQAMI: <b>{booklet_num_str}</b>", ParagraphStyle('TopKitob', fontName=FONT_NAME, fontSize=13, leading=15, alignment=1)),
            Paragraph(f"TIP: <b>{tip_code}</b>", ParagraphStyle('TopTip', fontName=FONT_NAME, fontSize=13, leading=15, alignment=1))
        ]
    ]
    top_box_table = Table(top_box_data, colWidths=[50, 310, 140], rowHeights=[40])
    top_box_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1.5, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(top_box_table)
    story.append(Spacer(1, 20))

    # 4. Government Headers
    story.append(Paragraph("O'ZBEKISTON RESPUBLIKASI VAZIRLAR MAHKAMASI", ParagraphStyle('GovHeader1', fontName=FONT_BOLD, fontSize=10, leading=12, alignment=1, textColor=colors.HexColor('#2D3748'))))
    story.append(Paragraph("DAVLAT TEST MARKAZI", ParagraphStyle('GovHeader2', fontName=FONT_BOLD, fontSize=10, leading=12, alignment=1, textColor=colors.HexColor('#2D3748'), spaceAfter=15)))
    story.append(Paragraph("REPETITSION TEST TOPSHIRUVCHILAR UCHUN", ParagraphStyle('GovHeader3', fontName=FONT_BOLD, fontSize=9, leading=11, alignment=1, textColor=colors.HexColor('#4A5568'), spaceAfter=15)))
    story.append(Paragraph("TEST TOPSHIRIQLARI<br/>KITOBI", ParagraphStyle('GovHeaderMain', fontName=FONT_BOLD, fontSize=22, leading=26, alignment=1, textColor=colors.HexColor('#1A202C'), spaceAfter=25)))

    # 5. Middle Layout: OMR Bubble Grid (Left) + Subject List Table (Right)
    # 5.1 OMR Bubble Grid helper
    def get_omr_bubble(char, is_shaded):
        d = Drawing(14, 14)
        if is_shaded:
            d.add(Circle(7, 7, 6.5, fillColor=colors.HexColor('#090f1d'), strokeColor=colors.HexColor('#090f1d')))
            d.add(String(7, 4.5, char, textAnchor='middle', fontName=FONT_BOLD, fontSize=8, fillColor=colors.white))
        else:
            d.add(Circle(7, 7, 6.5, fillColor=colors.white, strokeColor=colors.HexColor('#2D3748')))
            d.add(String(7, 4, char, textAnchor='middle', fontName=FONT_NAME, fontSize=7.5, fillColor=colors.HexColor('#2D3748')))
        return d

    # 5.2 Build Bubble Grid Table
    digits_row = [Paragraph(f"<b>{d}</b>", ParagraphStyle('DigitCol', fontName=FONT_BOLD, fontSize=10, leading=12, alignment=1)) for d in booklet_num_str]
    grid_data = []
    grid_data.append(digits_row)
    for r in range(10):
        row_cells = []
        for c in range(7):
            digit_val = int(booklet_num_str[c])
            is_shaded = (r == digit_val)
            row_cells.append(get_omr_bubble(str(r), is_shaded))
        grid_data.append(row_cells)

    grid_table = Table(grid_data, colWidths=[18]*7, rowHeights=[18]*11)
    grid_style = TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOX', (0,0), (-1,-1), 0.75, colors.black),
        ('GRID', (0,0), (-1,0), 0.75, colors.black),
        ('LINEBEFORE', (1,0), (1,-1), 0.5, colors.black),
        ('LINEBEFORE', (2,0), (2,-1), 0.5, colors.black),
        ('LINEBEFORE', (3,0), (3,-1), 0.5, colors.black),
        ('LINEBEFORE', (4,0), (4,-1), 0.5, colors.black),
        ('LINEBEFORE', (5,0), (5,-1), 0.5, colors.black),
        ('LINEBEFORE', (6,0), (6,-1), 0.5, colors.black),
    ])
    grid_table.setStyle(grid_style)

    left_cell_flowables = [
        Paragraph("Test topshiriqlari<br/>kitobi raqami", ParagraphStyle('GridTitle', fontName=FONT_NAME, fontSize=8, leading=10, alignment=1, spaceAfter=5)),
        grid_table
    ]

    # 5.3 Build Subject List Table
    subject_table_data = [
        [
            Paragraph("<b>1-30</b> topshiriqlar", ParagraphStyle('SubText1', fontName=FONT_NAME, fontSize=10)),
            Paragraph("<i>Majburiy fanlar</i>", ParagraphStyle('SubText2', fontName=FONT_ITALIC, fontSize=10))
        ],
        [
            Paragraph(f"<b>31-60</b> topshiriqlar", ParagraphStyle('SubText1', fontName=FONT_NAME, fontSize=10)),
            Paragraph(f"<i>{registration.block1_subject}</i>", ParagraphStyle('SubText2', fontName=FONT_ITALIC, fontSize=10))
        ],
        [
            Paragraph(f"<b>61-90</b> topshiriqlar", ParagraphStyle('SubText1', fontName=FONT_NAME, fontSize=10)),
            Paragraph(f"<i>{registration.block2_subject}</i>", ParagraphStyle('SubText2', fontName=FONT_ITALIC, fontSize=10))
        ]
    ]
    subject_table = Table(subject_table_data, colWidths=[120, 200], rowHeights=[20]*3)
    subject_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))

    right_cell_flowables = [
        Spacer(1, 15),
        subject_table
    ]

    middle_layout_table = Table([[left_cell_flowables, right_cell_flowables]], colWidths=[180, 343])
    middle_layout_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 20),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(middle_layout_table)
    story.append(Spacer(1, 20))

    # 6. Bottom Layout: Rules Box (Left) + Candidate Fields (Right)
    rules_text = """
    <font size="8"><b>ABITURIYENT DIQQATIGA!</b><br/><br/>
    1. Har bir majburiy fandan 10 tadan, mutaxassislik fanlaridan 30 tadan test topshirig'i <b>mavjudligini tekshiring</b>.<br/><br/>
    2. Nuqsonlar aniqlanganda <b>darhol</b> guruh nazoratchisiga <b>ma'lum qiling</b>.<br/><br/>
    3. Ushbu kitob raqamini javoblar varaqasiga <b>ko'chiring</b>.<br/><br/>
    4. Kitob muqovasiga o'zingiz haqingizdagi <b>ma'lumotlarni yozing</b> va <b>imzo qo'ying</b>.<br/><br/>
    5. Ushbu kitob guruh nazoratchisiga <b>topshirilishi shart</b>.</font>
    """
    rules_box = Table([[Paragraph(rules_text, ParagraphStyle('RulesBoxText', fontName=FONT_NAME, fontSize=8, leading=10.5))]], colWidths=[220])
    rules_box.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    
    details_text = f"""
    Familiyangiz: <b>{registration.student.last_name}</b><br/>
    <font color="#000000"><b>_____________________________________________________</b></font><br/><br/>
    Ismingiz: <b>{registration.student.first_name}</b><br/>
    <font color="#000000"><b>_____________________________________________________</b></font><br/><br/>
    Otangizning ismi:<br/>
    <font color="#000000"><b>_____________________________________________________</b></font><br/><br/>
    <font size="8">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.........................................................................<br/>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Imzo</font><br/><br/>
    <font size="7.5"><b>Yuqoridagi ma'lumotlar qayd etilmagan yoki kitobga shikast yetkazilgan hollarda e'tirozlar ko'rib chiqilmaydi.</b></font>
    """
    details_paragraph = Paragraph(details_text, ParagraphStyle('DetailsText', fontName=FONT_NAME, fontSize=8.5, leading=12))

    bottom_layout_table = Table([[rules_box, details_paragraph]], colWidths=[240, 283])
    bottom_layout_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(bottom_layout_table)
    story.append(Spacer(1, 15))

    # Copyright footer
    story.append(Paragraph("Davlat test markazi &copy; 2022", ParagraphStyle('CopyrightText', fontName=FONT_NAME, fontSize=8, alignment=0, textColor=colors.HexColor('#718096'))))

    # NextPageTemplate & PageBreak
    story.append(NextPageTemplate('TwoCols'))
    story.append(PageBreak())

    def get_image_tag(filename):
        from django.conf import settings
        from PIL import Image as PILImage
        full_path = os.path.join(settings.MEDIA_ROOT, 'dtm_images', filename)
        if os.path.exists(full_path):
            try:
                with PILImage.open(full_path) as img:
                    w, h = img.size
                    max_w = 180
                    if w > max_w:
                        h = int(h * (max_w / w))
                        w = max_w
                    return f'<br/><br/><img src="{full_path}" width="{w}" height="{h}"/><br/><br/>'
            except Exception:
                pass
        return ""

    import re

    # 7. Render Booklet Questions
    for item in pdf_content_sections:
        if item['type'] == 'header':
            story.append(Spacer(1, 8))
            story.append(Paragraph(item['text'], section_header_style))
            story.append(Spacer(1, 4))
        elif item['type'] == 'question':
            q_flowables = []
            
            # Question body to flowables
            question_flowables = text_to_flowables(item['text'], question_style, number_prefix=f"<b>{item['number']}.</b>")
            q_flowables.extend(question_flowables)
            
            # Options list to flowables
            for o_idx, opt in enumerate(item['options']):
                letter = chr(65 + o_idx)
                cleaned_opt = clean_option_text(opt)
                option_flowables = text_to_flowables(cleaned_opt, option_style, number_prefix=f"<b>{letter})</b>")
                q_flowables.extend(option_flowables)
                
            story.append(KeepTogether(q_flowables))

    doc.build(story)
    buffer.seek(0)
    
    # Save the generated PDF file to booklet_file
    registration.booklet_file.save(f"booklet_{booklet_num}.pdf", ContentFile(buffer.read()))
    registration.save()

    messages.success(request, f"{registration.student.get_full_name()} uchun test kitobchasi ({booklet_num}) muvaffaqiyatli shakllantirildi!")
    return redirect('admin_dtm_registrations', exam_id=exam.id)


@subadmin_permission_required('manage_dtm')
def admin_dtm_omr_scan(request):

    if request.method == 'POST':
        omr_image = request.FILES.get('omr_image')
        if not omr_image:
            messages.error(request, "Iltimos, javoblar varaqasi rasmini yuklang!")
            return redirect('admin_dtm_omr_scan')

        try:
            image = PILImage.open(omr_image)
            api_key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Gemini API kaliti topilmadi.")

            client = genai.Client(api_key=api_key)

            prompt = """
            Skanerlangan DTM javoblar varag'ining rasmini tahlil qil.
            Ushbu rasmdan quyidagilarni aniq o'qib ber:
            1. "KITOBCHA RAQAMI" (Booklet Number) - 6 xonali raqam (masalan, 481029). Uni rasm tepasidagi maxsus katakchalardan aniqlang.
            2. Talabaning har bir savol (1 dan boshlab) uchun belgilangan javob varianti (A, B, C yoki D). Bo'yalgan doirachalarni diqqat bilan tekshiring. Agar doiracha bo'yalmagan bo'lsa, javobni bo'sh qoldiring (masalan, null yoki "").
            
            Natijani faqat taqdim etilgan OMRScannedResult Pydantic sxemasiga mos ravishda JSON formatida qaytaring.
            """

            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OMRScannedResult,
                    temperature=0.1
                )
            )

            result_data = json.loads(response.text)
            booklet_num = result_data.get('booklet_number')
            student_answers = result_data.get('answers', {})

            # DTM Registrationni topamiz
            registration = DTMRegistration.objects.filter(booklet_number=booklet_num).select_related('student', 'exam').first()
            if not registration:
                messages.error(request, f"Kitobcha raqami topilmadi: {booklet_num}")
                return redirect('admin_dtm_omr_scan')

            # Kalitni o'qiymiz
            if not registration.booklet_answers_key:
                messages.error(request, f"Ushbu kitobcha ({booklet_num}) uchun javoblar kaliti generatsiya qilinmagan!")
                return redirect('admin_dtm_omr_scan')

            correct_answers_map = json.loads(registration.booklet_answers_key)
            exam = registration.exam

            # Ballarni hisoblash
            block1_correct = 0
            block2_correct = 0
            compulsory_correct = 0

            # Savollar turlarini aniqlash
            # Majburiy fanlar savol indeksi 1 dan boshlanadi va (compulsory_questions_count * 3) gacha boradi (agar topshirgan bo'lsa)
            comp_limit = (exam.compulsory_questions_count * 3) if registration.take_compulsory else 0
            block1_start = comp_limit + 1
            block1_end = comp_limit + exam.block1_questions_count
            block2_start = block1_end + 1
            block2_end = block1_end + exam.block2_questions_count

            for q_num_str, details in correct_answers_map.items():
                q_num = int(q_num_str)
                correct_letter = details.get('correct_letter')
                student_choice = student_answers.get(q_num_str, '').upper().strip()

                if student_choice == correct_letter:
                    if q_num <= comp_limit:
                        compulsory_correct += 1
                    elif block1_start <= q_num <= block1_end:
                        block1_correct += 1
                    elif block2_start <= q_num <= block2_end:
                        block2_correct += 1

            score_b1 = block1_correct * exam.block1_score
            score_b2 = block2_correct * exam.block2_score
            score_comp = compulsory_correct * exam.compulsory_score
            total_score = score_b1 + score_b2 + score_comp

            # Natijani saqlaymiz
            result_obj, created = StudentDTMExamResult.objects.update_or_create(
                registration=registration,
                defaults={
                    'score_block1': score_b1,
                    'score_block2': score_b2,
                    'score_compulsory': score_comp,
                    'total_score': total_score,
                    'student_answers_raw': json.dumps(student_answers)
                }
            )

            student_name = escape(registration.student.get_full_name() or registration.student.username)
            messages.success(
                request,
                f"Natija muvaffaqiyatli aniqlandi! Talaba: <b>{student_name}</b>. "
                f"1-blok: {block1_correct}/{exam.block1_questions_count} ({score_b1} ball). "
                f"2-blok: {block2_correct}/{exam.block2_questions_count} ({score_b2} ball). "
                f"Majburiy: {compulsory_correct}/{comp_limit} ({score_comp} ball). "
                f"Umumiy ball: <b>{total_score} ball</b>!"
            )
            return redirect('admin_dtm_registrations', exam_id=exam.id)

        except Exception as e:
            messages.error(request, f"Rasm tahlil qilishda xatolik yuz berdi: {str(e)}")
            return redirect('admin_dtm_omr_scan')

    return render(request, 'admin_dtm_omr_scan.html')


@subadmin_permission_required('manage_dtm')
def admin_dtm_results_view(request, exam_id):

    exam = get_object_or_404(DTMExam, id=exam_id)
    results = StudentDTMExamResult.objects.filter(registration__exam=exam).select_related('registration__student').order_by('-total_score')
    
    return render(request, 'admin_dtm_results.html', {
        'exam': exam,
        'results': results
    })


@login_required
def dtm_bubble_sheet_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="dtm_javoblar_varaqasi.pdf"'
    
    c = canvas.Canvas(response, pagesize=A4)
    
    # 1. Draw Corner Alignment Marks (Anchor Crosshairs / Boxes)
    c.setFillColor(colors.black)
    c.rect(20, 802, 15, 15, fill=1) # Top Left
    c.rect(560, 802, 15, 15, fill=1) # Top Right
    c.rect(20, 20, 15, 15, fill=1) # Bottom Left
    c.rect(560, 20, 15, 15, fill=1) # Bottom Right
    
    # 2. Draw Government-style Header
    c.setFont(FONT_BOLD, 10)
    c.drawCentredString(297, 805, "O'ZBEKISTON RESPUBLIKASI MOCK TEST TIZIMI")
    c.setFont(FONT_BOLD, 14)
    c.drawCentredString(297, 785, "JAVOBLAR VARAQASI (OMR ANSWER SHEET)")
    
    # 3. Draw Student Details Box (Nomzod Ma'lumotlari)
    c.rect(40, 600, 310, 160)
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(colors.HexColor('#1A365D'))
    c.drawString(50, 742, "NOMZOD MA'LUMOTLARI:")
    
    c.setFillColor(colors.black)
    c.setFont(FONT_NAME, 9)
    # F.I.SH.
    c.drawString(50, 715, "Familiyangiz:")
    c.line(120, 715, 335, 715)
    c.drawString(50, 695, "Ismingiz:")
    c.line(100, 695, 335, 695)
    c.drawString(50, 675, "Otangizning ismi:")
    c.line(135, 675, 335, 675)
    
    # Group and Date
    c.drawString(50, 645, "Guruhi:")
    c.line(90, 645, 195, 645)
    c.drawString(205, 645, "Sana:")
    c.line(235, 645, 335, 645)
    
    # Signature
    c.drawString(50, 615, "Nomzod imzosi:")
    c.line(130, 615, 335, 615)
    
    # 4. Draw Booklet Number Grid (7 digit bubble grid)
    c.rect(370, 600, 185, 160)
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(colors.HexColor('#1A365D'))
    c.drawCentredString(462, 742, "TEST KITOBI RAQAMI")
    
    # Draw 7 digit writing boxes
    c.setFillColor(colors.black)
    c.setFont(FONT_BOLD, 8)
    for i in range(7):
        box_x = 380 + i * 24
        # Draw digit writing box at top
        c.rect(box_x, 715, 18, 16)
        
        # Draw bubble column for digits 0-9
        for r in range(10):
            bubble_y = 695 - r * 9.5
            # Draw circle
            c.circle(box_x + 9, bubble_y + 3, 4.5, stroke=1, fill=0)
            # Draw digit inside circle
            c.drawCentredString(box_x + 9, bubble_y + 0.5, str(r))
            
    # 5. Draw Bubble Grid for 90 questions (3 columns of 30)
    cols_x = [40, 225, 410]
    labels = ["MAJBURIY FANLAR (1-30)", "1-MUTAXASSISLIK (31-60)", "2-MUTAXASSISLIK (61-90)"]
    
    for col_idx, start_q in enumerate([1, 31, 61]):
        x_base = cols_x[col_idx]
        
        # Column title block
        c.setFillColor(colors.HexColor('#EDF2F7'))
        c.rect(x_base, 555, 145, 18, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#1A365D'))
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(x_base + 72.5, 560, labels[col_idx])
        
        c.setFillColor(colors.black)
        for row_idx in range(30):
            q_num = start_q + row_idx
            y = 535 - (row_idx * 15.5)
            
            # Draw question number
            c.setFont(FONT_BOLD, 9)
            c.drawString(x_base, y + 1, f"{q_num:2d}.")
            
            # Draw A, B, C, D bubbles
            c.setFont(FONT_NAME, 7.5)
            options = ["A", "B", "C", "D"]
            for opt_idx, opt in enumerate(options):
                opt_x = x_base + 22 + (opt_idx * 30)
                # Draw circle
                c.circle(opt_x + 6, y + 4, 5.5, stroke=1, fill=0)
                # Draw letter inside
                c.drawCentredString(opt_x + 6, y + 1.5, opt)
                
    # 6. Draw copyright footer
    c.setFont(FONT_BOLD, 8)
    c.setFillColor(colors.HexColor("#718096"))
    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "Tizim"
    c.drawString(40, 42, f"{site_name.upper()} MOCK DTM TIZIMI")
    c.drawRightString(555, 42, "SUN'IY INTELLEKT OMR SKANERI TAYYOR")
    
    c.showPage()
    c.save()
    return response


# ==========================================
# 📝 DTM QUESTION POOL EDITING VIEWS
# ==========================================
from django.core.paginator import Paginator
from main.models import DTMQuestionPool, DTMAnswerPool

@subadmin_permission_required('manage_dtm')
def admin_dtm_questions_list(request):

    subject_filter = request.GET.get('subject', '')
    difficulty_filter = request.GET.get('difficulty', '')
    compulsory_filter = request.GET.get('is_compulsory', '')

    questions = DTMQuestionPool.objects.all().prefetch_related('answers').order_by('-id')

    if subject_filter:
        questions = questions.filter(subject=subject_filter)
    if difficulty_filter:
        questions = questions.filter(difficulty=int(difficulty_filter))
    if compulsory_filter:
        questions = questions.filter(is_compulsory=(compulsory_filter == 'true'))

    # Paginate by 50 questions
    paginator = Paginator(questions, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    subjects = DTMQuestionPool.objects.values_list('subject', flat=True).distinct().order_by('subject')

    return render(request, 'admin_dtm_questions_list.html', {
        'page_obj': page_obj,
        'subjects': subjects,
        'subject_filter': subject_filter,
        'difficulty_filter': difficulty_filter,
        'compulsory_filter': compulsory_filter,
    })


@subadmin_permission_required('manage_dtm')
@transaction.atomic
def admin_dtm_question_edit(request, question_id):
    question = get_object_or_404(DTMQuestionPool, id=question_id)
    answers = list(question.answers.all().order_by('id'))

    import re
    import os
    import uuid
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile

    if request.method == 'POST':
        question.subject = request.POST.get('subject')
        question.difficulty = int(request.POST.get('difficulty', 2))
        question.is_compulsory = request.POST.get('is_compulsory') == 'on'
        
        text = request.POST.get('text', '')
        
        # Handle diagram image upload
        uploaded_image = request.FILES.get('diagram_image')
        if uploaded_image:
            ext = os.path.splitext(uploaded_image.name)[1] or '.png'
            filename = f"img_manual_{uuid.uuid4().hex[:12]}{ext}"
            default_storage.save(f"dtm_images/{filename}", ContentFile(uploaded_image.read()))
            
            # Replace existing placeholder if present, else append it
            if "[DIAGRAM_IMAGE:" in text:
                text = re.sub(r'\[DIAGRAM_IMAGE:[^\]]+\]', f"[DIAGRAM_IMAGE:{filename}]", text, count=1)
            else:
                text += f" [DIAGRAM_IMAGE:{filename}]"
        
        question.text = text
        question.save()

        # Update or create the 4 options
        correct_index = int(request.POST.get('correct_option', 1)) - 1  # 0-indexed

        for i in range(4):
            opt_num = i + 1
            opt_text = request.POST.get(f'option_{opt_num}', '')
            
            # Check for uploaded image for this option
            uploaded_opt_image = request.FILES.get(f'option_image_{opt_num}')
            if uploaded_opt_image:
                ext = os.path.splitext(uploaded_opt_image.name)[1] or '.png'
                opt_image_filename = f"img_manual_opt_{uuid.uuid4().hex[:12]}{ext}"
                default_storage.save(f"dtm_images/{opt_image_filename}", ContentFile(uploaded_opt_image.read()))
                
                # Replace existing placeholder if present, else append it
                if "[DIAGRAM_IMAGE:" in opt_text:
                    opt_text = re.sub(r'\[DIAGRAM_IMAGE:[^\]]+\]', f"[DIAGRAM_IMAGE:{opt_image_filename}]", opt_text, count=1)
                else:
                    opt_text += f" [DIAGRAM_IMAGE:{opt_image_filename}]"
            
            is_corr = (i == correct_index)
            
            if i < len(answers):
                # Update existing answer
                ans = answers[i]
                ans.text = opt_text
                ans.is_correct = is_corr
                ans.save()
            else:
                # Create if missing
                DTMAnswerPool.objects.create(
                    question=question,
                    text=opt_text,
                    is_correct=is_corr
                )

        messages.success(request, "Savol va uning javob variantlari muvaffaqiyatli tahrirlandi.")
        return redirect('admin_dtm_questions_list')

    # Ensure exactly 4 options are in the context for rendering
    while len(answers) < 4:
        answers.append(None)

    # Parse current diagram image filename from text for preview
    current_image = None
    if question.text:
        match = re.search(r'\[DIAGRAM_IMAGE:([^\]]+)\]', question.text)
        if match:
            current_image = match.group(1)

    subjects = ["Matematika", "Fizika", "Kimyo", "Biologiya", "Ingliz tili", "Ona tili", "Tarix", "Geografiya"]

    return render(request, 'admin_dtm_question_edit.html', {
        'question': question,
        'answers': answers,
        'subjects': subjects,
        'current_image': current_image,
    })


@subadmin_permission_required('manage_dtm')
def admin_dtm_question_delete(request, question_id):
    question = get_object_or_404(DTMQuestionPool, id=question_id)
    question.delete()
    messages.success(request, "Savol bazadan butunlay o'chirildi.")
    return redirect('admin_dtm_questions_list')


@subadmin_permission_required('manage_dtm')
@transaction.atomic
def admin_dtm_question_add(request):
    subjects = ["Matematika", "Fizika", "Kimyo", "Biologiya", "Ingliz tili", "Ona tili", "Tarix", "Geografiya"]

    import os
    import uuid
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile

    if request.method == 'POST':
        subject = request.POST.get('subject')
        difficulty = int(request.POST.get('difficulty', 2))
        is_compulsory = request.POST.get('is_compulsory') == 'on'
        text = request.POST.get('text', '')

        # Handle diagram image upload
        uploaded_image = request.FILES.get('diagram_image')
        if uploaded_image:
            ext = os.path.splitext(uploaded_image.name)[1] or '.png'
            filename = f"img_manual_{uuid.uuid4().hex[:12]}{ext}"
            default_storage.save(f"dtm_images/{filename}", ContentFile(uploaded_image.read()))
            text += f" [DIAGRAM_IMAGE:{filename}]"

        # Create question
        question = DTMQuestionPool.objects.create(
            subject=subject,
            difficulty=difficulty,
            is_compulsory=is_compulsory,
            text=text
        )

        correct_index = int(request.POST.get('correct_option', 1)) - 1  # 0-indexed

        answers_to_create = []
        for i in range(4):
            opt_text = request.POST.get(f'option_{i+1}')
            is_corr = (i == correct_index)
            answers_to_create.append(
                DTMAnswerPool(
                    question=question,
                    text=opt_text,
                    is_correct=is_corr
                )
            )
        DTMAnswerPool.objects.bulk_create(answers_to_create)

        messages.success(request, "Yangi savol muvaffaqiyatli qo'shildi.")
        return redirect('admin_dtm_questions_list')

    answers = [None, None, None, None]

    return render(request, 'admin_dtm_question_edit.html', {
        'question': None,
        'answers': answers,
        'subjects': subjects,
        'current_image': None,
    })



@subadmin_permission_required('manage_subjects')
def subject_list_admin(request):

    subjects = Subject.objects.all().order_by('-created_at')
    return render(request, 'subject_list_admin.html', {'subjects': subjects})


@subadmin_permission_required('manage_subjects')
def create_subject_admin(request):

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Fan nomi bo'sh bo'lishi mumkin emas.")
            return redirect('create_subject_admin')

        if Subject.objects.filter(name=name).exists():
            messages.error(request, "Ushbu nomdagi fan allaqachon mavjud.")
            return redirect('create_subject_admin')

        subject = Subject.objects.create(name=name, description=description)
        log_action(request.user, "Fan Yaratildi", f"Yangi fan yaratildi: {subject.name} (ID: {subject.id})", request)
        messages.success(request, "Yangi fan muvaffaqiyatli qo'shildi.")
        return redirect('subject_list_admin')

    return render(request, 'subject_create_admin.html')


@subadmin_permission_required('manage_subjects')
def edit_subject_admin(request, subject_id):

    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == 'POST':
        if 'delete' in request.POST:
            subject_name = subject.name
            subject_id_val = subject.id
            subject.delete()
            log_action(request.user, "Fan O'chirildi", f"Fan o'chirildi: {subject_name} (ID: {subject_id_val})", request)
            messages.success(request, "Fan muvaffaqiyatli o'chirildi.")
            return redirect('subject_list_admin')

        # Handle material upload action
        if request.POST.get('action') == 'upload_material':
            material_file = request.FILES.get('material_file')
            if material_file:
                title = request.POST.get('material_title', '').strip()
                if not title:
                    title = material_file.name
                description = request.POST.get('material_description', '').strip()
                
                SubjectMaterial.objects.create(
                    subject=subject,
                    title=title,
                    description=description,
                    file=material_file,
                    uploaded_by=request.user
                )
                messages.success(request, "Yangi material muvaffaqiyatli yuklandi.")
            else:
                messages.error(request, "Fayl tanlanmagan.")
            return redirect('edit_subject_admin', subject_id=subject.id)

        # Handle book upload action
        if request.POST.get('action') == 'upload_book':
            book_file = request.FILES.get('book_file')
            if book_file:
                if not book_file.name.lower().endswith('.pdf'):
                    messages.error(request, "Kitob faqat PDF formatida bo'lishi kerak.")
                    return redirect('edit_subject_admin', subject_id=subject.id)
                
                title = request.POST.get('book_title', '').strip()
                if not title:
                    title = book_file.name
                description = request.POST.get('book_description', '').strip()
                
                Book.objects.create(
                    subject=subject,
                    title=title,
                    description=description,
                    file=book_file,
                    uploaded_by=request.user
                )
                log_action(request.user, "Kitob Yuklandi (Admin)", f"Yangi kitob yuklandi: '{title}' (Fan: {subject.name})", request)
                messages.success(request, "Yangi kitob muvaffaqiyatli yuklandi.")
            else:
                messages.error(request, "Fayl tanlanmagan.")
            return redirect('edit_subject_admin', subject_id=subject.id)

        # Handle subject edit action
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Fan nomi bo'sh bo'lishi mumkin emas.")
            return redirect('edit_subject_admin', subject_id=subject.id)

        if Subject.objects.filter(name=name).exclude(id=subject.id).exists():
            messages.error(request, "Ushbu nomdagi fan allaqachon mavjud.")
            return redirect('edit_subject_admin', subject_id=subject.id)

        subject.name = name
        subject.description = description
        subject.save()

        log_action(request.user, "Fan Tahrirlandi", f"Fan ma'lumotlari tahrirlandi: {subject.name} (ID: {subject.id})", request)
        messages.success(request, "Fan ma'lumotlari muvaffaqiyatli saqlandi.")
        return redirect('subject_list_admin')

    materials = subject.materials.all().order_by('-created_at')
    books = subject.books.all().order_by('-created_at')
    return render(request, 'subject_edit_admin.html', {
        'subject': subject,
        'materials': materials,
        'books': books
    })


@subadmin_permission_required('manage_subjects')
def delete_subject_material_admin(request, material_id):

    material = get_object_or_404(SubjectMaterial, id=material_id)
    subject_id = material.subject_id
    material_title = material.title
    material.delete()
    log_action(request.user, "Fan Materiali O'chirildi", f"Fan materiali o'chirildi: {material_title} (Fan ID: {subject_id})", request)
    messages.success(request, "Material muvaffaqiyatli o'chirildi.")
    return redirect('edit_subject_admin', subject_id=subject_id)


@subadmin_permission_required('manage_subjects')
def delete_book_admin(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    subject_id = book.subject_id
    book_title = book.title
    
    # Delete from storage
    if book.file:
        if os.path.exists(book.file.path):
            os.remove(book.file.path)
            
    book.delete()
    log_action(request.user, "Kitob O'chirildi (Admin)", f"Kitob o'chirildi: {book_title} (Fan ID: {subject_id})", request)
    messages.success(request, "Kitob muvaffaqiyatli o'chirildi.")
    return redirect('edit_subject_admin', subject_id=subject_id)


@subadmin_permission_required('manage_subjects')
def admin_books_report_view(request):
    books = Book.objects.select_related('subject', 'uploaded_by').order_by('-created_at')
    
    # Map subject_id -> list of Group objects to avoid N+1 query issues
    subject_groups = defaultdict(list)
    for g in Group.objects.select_related('subject').all():
        if g.subject_id:
            subject_groups[g.subject_id].append(g)
            
    report_data = []
    for book in books:
        groups = subject_groups.get(book.subject_id, [])
        report_data.append({
            'book': book,
            'groups': groups,
        })
        
    return render(request, 'admin_books_report.html', {
        'report_data': report_data
    })


@role_required(['admin', 'reception'])
def admin_salaries_view(request):
    current_date = timezone.now()
    month_val = int(request.GET.get('month', current_date.month))
    year_val = int(request.GET.get('year', current_date.year))
    
    months_list = [
        (1, "Yanvar"), (2, "Fevral"), (3, "Mart"), (4, "Aprel"),
        (5, "May"), (6, "Iyun"), (7, "Iyul"), (8, "Avgust"),
        (9, "Sentabr"), (10, "Oktabr"), (11, "Noyabr"), (12, "Dekabr")
    ]
    
    teachers = CustomUser.objects.filter(role='teacher').prefetch_related('teachers_groups', 'teachers_groups__subject')
    
    month_name = dict(months_list)[month_val]
    month_str = f"{month_name} {year_val}"
    
    payments = StudentPayment.objects.filter(paid_at__month=month_val, paid_at__year=year_val).select_related('group')
    
    group_payments = defaultdict(float)
    for pay in payments:
        group_payments[pay.group_id] += float(pay.amount_paid)
        
    lessons = GroupLesson.objects.filter(date__month=month_val, date__year=year_val).values('group_id').annotate(count=Count('id'))
    group_lessons = {item['group_id']: item['count'] for item in lessons}
    
    salary_payments = TeacherSalaryPayment.objects.filter(month=month_str).values('teacher_id', 'group_id').annotate(total_paid=Sum('amount'))
    paid_lookup = {}
    for p in salary_payments:
        paid_lookup[(p['teacher_id'], p['group_id'])] = float(p['total_paid'] or 0)
        
    salary_report = []
    total_earned_overall = 0
    total_paid_overall = 0
    
    for teacher in teachers:
        teacher_groups_data = []
        teacher_earned = 0.0
        teacher_paid = 0.0
        teacher_lessons = 0
        teacher_revenue = 0.0
        
        for group in teacher.teachers_groups.all():
            lessons_count = group_lessons.get(group.id, 0)
            total_collected = group_payments.get(group.id, 0.0)
            
            earned = 0.0
            if group.salary_type == 'percent':
                earned = total_collected * float(group.salary_rate) / 100.0
            elif group.salary_type == 'fixed':
                earned = lessons_count * float(group.salary_rate)
                
            already_paid = paid_lookup.get((teacher.id, group.id), 0.0)
            balance = earned - already_paid
            
            teacher_earned += earned
            teacher_paid += already_paid
            teacher_lessons += lessons_count
            teacher_revenue += total_collected
            
            total_earned_overall += earned
            total_paid_overall += already_paid
            
            teacher_groups_data.append({
                'group': group,
                'lessons_count': lessons_count,
                'total_collected': total_collected,
                'earned': earned,
                'already_paid': already_paid,
                'balance': balance
            })
            
        salary_report.append({
            'teacher': teacher,
            'groups_data': teacher_groups_data,
            'total_earned': teacher_earned,
            'total_paid': teacher_paid,
            'balance': teacher_earned - teacher_paid,
            'total_lessons': teacher_lessons,
            'total_revenue': teacher_revenue
        })
        
    recent_salary_payments = TeacherSalaryPayment.objects.select_related('teacher', 'group', 'paid_by').order_by('-paid_at')[:10]
    
    # 6 oylik trend ma'lumotlari (Revenue vs Payroll)
    trend_labels = []
    trend_revenues = []
    trend_payrolls = []
    
    for i in range(5, -1, -1):
        target_year = year_val
        target_month = month_val - i
        while target_month <= 0:
            target_month += 12
            target_year -= 1
            
        t_month_name = dict(months_list)[target_month]
        t_month_str = f"{t_month_name} {target_year}"
        
        rev = StudentPayment.objects.filter(paid_at__month=target_month, paid_at__year=target_year).aggregate(total=Sum('amount_paid'))['total'] or 0.0
        pay = TeacherSalaryPayment.objects.filter(month=t_month_str).aggregate(total=Sum('amount'))['total'] or 0.0
        
        trend_labels.append(f"{t_month_name[:3]} {target_year}")
        trend_revenues.append(float(rev))
        trend_payrolls.append(float(pay))
        
    return render(request, 'admin_salaries.html', {
        'salary_report': salary_report,
        'months_list': months_list,
        'selected_month': month_val,
        'selected_year': year_val,
        'month_str': month_str,
        'total_earned_overall': total_earned_overall,
        'total_paid_overall': total_paid_overall,
        'total_balance_overall': total_earned_overall - total_paid_overall,
        'recent_salary_payments': recent_salary_payments,
        'trend_labels': trend_labels,
        'trend_revenues': trend_revenues,
        'trend_payrolls': trend_payrolls
    })


@role_required(['admin', 'reception'])
def admin_export_salaries_csv(request):
    current_date = timezone.now()
    month_val = int(request.GET.get('month', current_date.month))
    year_val = int(request.GET.get('year', current_date.year))
    
    months_list = [
        (1, "Yanvar"), (2, "Fevral"), (3, "Mart"), (4, "Aprel"),
        (5, "May"), (6, "Iyun"), (7, "Iyul"), (8, "Avgust"),
        (9, "Sentabr"), (10, "Oktabr"), (11, "Noyabr"), (12, "Dekabr")
    ]
    
    teachers = CustomUser.objects.filter(role='teacher').prefetch_related('teachers_groups', 'teachers_groups__subject')
    
    month_name = dict(months_list)[month_val]
    month_str = f"{month_name} {year_val}"
    
    payments = StudentPayment.objects.filter(paid_at__month=month_val, paid_at__year=year_val).select_related('group')
    group_payments = defaultdict(float)
    for pay in payments:
        group_payments[pay.group_id] += float(pay.amount_paid)
        
    lessons = GroupLesson.objects.filter(date__month=month_val, date__year=year_val).values('group_id').annotate(count=Count('id'))
    group_lessons = {item['group_id']: item['count'] for item in lessons}
    
    salary_payments = TeacherSalaryPayment.objects.filter(month=month_str).values('teacher_id', 'group_id').annotate(total_paid=Sum('amount'))
    paid_lookup = {}
    for p in salary_payments:
        paid_lookup[(p['teacher_id'], p['group_id'])] = float(p['total_paid'] or 0)
        
    import tablib
    
    headers = [
        "O'qituvchi", "Guruh", "Fan", "O'tkazilgan darslar", 
        "Jami Tushum (UZS)", "Maosh turi", "Maosh tarifi", 
        "Hisoblangan oylik (UZS)", "To'langan oylik (UZS)", "Qoldiq (UZS)"
    ]
    data = tablib.Dataset(headers=headers)
    
    for teacher in teachers:
        for group in teacher.teachers_groups.all():
            lessons_count = group_lessons.get(group.id, 0)
            total_collected = group_payments.get(group.id, 0.0)
            
            earned = 0.0
            if group.salary_type == 'percent':
                earned = total_collected * float(group.salary_rate) / 100.0
            elif group.salary_type == 'fixed':
                earned = lessons_count * float(group.salary_rate)
                
            already_paid = paid_lookup.get((teacher.id, group.id), 0.0)
            balance = earned - already_paid
            
            salary_type_label = "Foizli" if group.salary_type == 'percent' else "Fixed (Darsbay)"
            salary_rate_label = f"{group.salary_rate}%" if group.salary_type == 'percent' else f"{group.salary_rate} UZS"
            
            data.append([
                f"{teacher.first_name} {teacher.last_name}",
                group.name,
                group.subject.name if group.subject else "-",
                lessons_count,
                total_collected,
                salary_type_label,
                salary_rate_label,
                earned,
                already_paid,
                balance
            ])
            
    response = HttpResponse(
        data.export('xlsx'),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=\"maoshlar_hisoboti_{month_val}_{year_val}.xlsx\"'
    return response


@role_required(['admin', 'reception'])
def admin_pay_teacher_salary(request):
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        group_id = request.POST.get('group_id')
        amount = request.POST.get('amount')
        month_str = request.POST.get('month_str')
        notes = request.POST.get('notes', '').strip()
        
        teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')
        group = get_object_or_404(Group, id=group_id)
        
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError()
        except ValueError:
            messages.error(request, "To'lov summasi noto'g'ri kiritildi.")
            return redirect('admin_salaries')
            
        TeacherSalaryPayment.objects.create(
            teacher=teacher,
            group=group,
            amount=amount_val,
            month=month_str,
            paid_by=request.user,
            notes=notes
        )
        log_action(request.user, "O'qituvchiga Oylik To'landi", f"O'qituvchi {teacher.first_name} {teacher.last_name}ga {group.name} guruhi uchun {month_str} oyi uchun {amount_val} UZS oylik maosh to'landi.", request)
        messages.success(request, f"O'qituvchi {teacher.first_name}ga oylik muvaffaqiyatli to'landi.")
        
    return redirect('admin_salaries')


@role_required(['admin', 'reception'])
def admin_wallets_view(request):
    students = CustomUser.objects.filter(role='student').order_by('-joined_at')
    recent_transactions = WalletTransaction.objects.select_related('student').order_by('-created_at')[:20]
    
    return render(request, 'admin_wallets.html', {
        'students': students,
        'recent_transactions': recent_transactions
    })


@role_required(['admin', 'reception'])
def admin_top_up_wallet(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        amount = request.POST.get('amount')
        description = request.POST.get('description', '').strip()
        
        student = get_object_or_404(CustomUser, id=student_id, role='student')
        
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError()
        except ValueError:
            messages.error(request, "To'ldirish summasi noto'g'ri kiritildi.")
            return redirect('admin_wallets')
            
        with transaction.atomic():
            student.balance = F('balance') + amount_val
            student.save()
            
            WalletTransaction.objects.create(
                student=student,
                amount=amount_val,
                transaction_type='top_up',
                description=description or "Hamyon to'ldirildi (Admin tomonidan)"
            )
            
        log_action(request.user, "Hamyon To'ldirildi", f"O'quvchi {student.first_name} {student.last_name}ning virtual hamyoni {amount_val} UZS ga to'ldirildi.", request)
        messages.success(request, f"{student.first_name} {student.last_name} hamyoni muvaffaqiyatli to'ldirildi.")
        
    return redirect('admin_wallets')


# ==========================================
# 🤖 DTM AI AUTO PARSE & FORMULA FORMAT APIS
# ==========================================
from pydantic import BaseModel
from typing import List
from django.http import JsonResponse


class DTMQuestionAIItem(BaseModel):
    text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: int
    subject: str
    difficulty: int
    is_compulsory: bool


class DTMQuestionsAIBatch(BaseModel):
    questions: List[DTMQuestionAIItem]


def repair_gemini_json(text):
    if not text:
        return {}
    import json, re

    clean_text = text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```[a-zA-Z]*\n?", "", clean_text)
        clean_text = re.sub(r"\n?```$", "", clean_text)
    clean_text = clean_text.strip()

    try:
        return json.loads(clean_text)
    except Exception:
        pass

    # Replace unescaped backslashes that are not valid JSON escape sequences
    fixed_text = re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', clean_text)

    try:
        return json.loads(fixed_text)
    except Exception:
        pass

    # Handle truncated JSON strings/brackets
    last_brace = fixed_text.rfind('}')
    if last_brace != -1:
        truncated = fixed_text[:last_brace+1]
        if not truncated.rstrip().endswith(']}'):
            if truncated.rstrip().endswith(']'):
                truncated += '}'
            else:
                truncated += ']}'
        try:
            return json.loads(truncated)
        except Exception:
            pass

    return {}


@subadmin_permission_required('manage_dtm')
def admin_dtm_ai_auto_parse_api(request):

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi"}, status=400)

    import json
    raw_text = ""
    file_bytes = None
    file_mime = None

    default_subject = request.POST.get('subject', 'Matematika')
    try:
        default_difficulty = int(request.POST.get('difficulty', 2))
    except (ValueError, TypeError):
        default_difficulty = 2
    default_compulsory = request.POST.get('is_compulsory') in ['true', 'on', True]

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
            raw_text = data.get('raw_text', '').strip()
            default_subject = data.get('subject', default_subject)
            default_difficulty = int(data.get('difficulty', default_difficulty))
            default_compulsory = data.get('is_compulsory', default_compulsory)
        except Exception:
            pass
    else:
        raw_text = request.POST.get('raw_text', '').strip()

    uploaded_file = request.FILES.get('document_file')
    if uploaded_file:
        fname = uploaded_file.name.lower()
        if fname.endswith('.txt'):
            raw_text = uploaded_file.read().decode('utf-8', errors='ignore')
        elif fname.endswith('.docx'):
            import docx
            doc = docx.Document(uploaded_file)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_txt:
                        paras.append(row_txt)
            raw_text = "\n".join(paras)
        elif fname.endswith('.pdf'):
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            pages = [page.extract_text() for page in reader.pages if page.extract_text()]
            raw_text = "\n".join(pages)
        elif fname.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            file_bytes = uploaded_file.read()
            if fname.endswith('.png'):
                file_mime = "image/png"
            elif fname.endswith('.webp'):
                file_mime = "image/webp"
            else:
                file_mime = "image/jpeg"

    if not raw_text and not file_bytes:
        return JsonResponse({'status': 'error', 'message': "Tahlil qilish uchun matn yoki fayl yuklanmadi"}, status=400)

    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        api_key = os.environ.get('GEMINI_API_KEY')

    parsed_questions = []

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            Siz DTM imtihon savollarini professional darajada tahlil qiluvchi va LaTeX/KaTeX formulalarini avtomatik formatlovchi AI tizimsiz.
            Berilgan fayl yoki matndan barcha savollarni va ularning 4 ta variantlarini ajratib oling:
            1. Har bir savol matnidagi (va variantlaridagi) barcha matematik, fizikaviy va kimyoviy formulalarni KaTeX $...$ (yoki alohida qatorda $$...$$) ko'rinishida mukammal LaTeX kodiga o'giring (masalan: $x^2 + y^2 = r^2$, \\frac{{a}}{{b}}, \\sqrt{{x}}, H_2O, \\int_4^{{20}}).
            2. Qaytariladigan ma'lumotlar to'g'ri shakllangan JSON formatida bo'lishi kerak. LaTeX belgilari JSON standartlariga muvofiq to'g'ri escape qilinishi lozim.
            3. Har bir savol uchun to'g'ri javob variantini aniqlang (1: A, 2: B, 3: C, 4: D).
            4. Fan nomini ({default_subject}) va qiyinchilik darajasini (1, 2 yoki 3) moslang.
            """

            contents = [prompt]
            if file_bytes and file_mime:
                contents.append(types.Part.from_bytes(data=file_bytes, mime_type=file_mime))
            if raw_text:
                contents.append(f"\n\nMatn:\n{raw_text}")

            try:
                response = client.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DTMQuestionsAIBatch,
                        temperature=0.1,
                        max_output_tokens=8192
                    )
                )
            except Exception as model_err:
                print(f"gemini-3-flash-preview failed, falling back to gemini-2.5-flash: {model_err}")
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DTMQuestionsAIBatch,
                        temperature=0.1,
                        max_output_tokens=8192
                    )
                )

            parsed_data = repair_gemini_json(response.text)
            def clean_latex(val):
                if not isinstance(val, str):
                    return val
                import re
                return re.sub(r'\\{2,}([a-zA-Z])', r'\\\1', val)

            for item in parsed_data.get('questions', []):
                parsed_questions.append({
                    'text': clean_latex(item.get('text', '')),
                    'option_a': clean_latex(item.get('option_a', '')),
                    'option_b': clean_latex(item.get('option_b', '')),
                    'option_c': clean_latex(item.get('option_c', '')),
                    'option_d': clean_latex(item.get('option_d', '')),
                    'correct_option': item.get('correct_option', 1),
                    'subject': item.get('subject', default_subject),
                    'difficulty': item.get('difficulty', default_difficulty),
                    'is_compulsory': item.get('is_compulsory', default_compulsory)
                })
        except Exception as e:
            print(f"Gemini DTM Parse Error: {str(e)}")

    if not parsed_questions and raw_text:
        import re
        blocks = re.split(r'\n(?=\d+[\.\)])', raw_text)
        for block in blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            q_text = lines[0]
            q_text = re.sub(r'^\d+[\.\)]\s*', '', q_text)

            opts = {'A': '', 'B': '', 'C': '', 'D': ''}
            correct_idx = 1

            for line in lines[1:]:
                match_opt = re.match(r'^([A-Da-d])[\.\)]\s*(.*)', line)
                if match_opt:
                    letter = match_opt.group(1).upper()
                    opts[letter] = match_opt.group(2)

                match_ans = re.search(r'(?:Javob|To\'g\'ri|Correct):\s*([A-Da-d])', line, re.IGNORECASE)
                if match_ans:
                    ans_let = match_ans.group(1).upper()
                    correct_idx = {'A': 1, 'B': 2, 'C': 3, 'D': 4}.get(ans_let, 1)

            if opts['A'] or opts['B']:
                parsed_questions.append({
                    'text': q_text,
                    'option_a': opts['A'],
                    'option_b': opts['B'],
                    'option_c': opts['C'],
                    'option_d': opts['D'],
                    'correct_option': correct_idx,
                    'subject': default_subject,
                    'difficulty': default_difficulty,
                    'is_compulsory': default_compulsory
                })

    return JsonResponse({'status': 'success', 'questions': parsed_questions})


@subadmin_permission_required('manage_dtm')
def admin_dtm_format_formula_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi"}, status=400)

    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        text = data.get('text', '').strip()
    except Exception:
        text = request.POST.get('text', '').strip()

    if not text:
        return JsonResponse({'status': 'success', 'formatted_text': ''})

    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        api_key = os.environ.get('GEMINI_API_KEY')

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = """
            Siz matematik va fizikaviy formulalarni toza KaTeX/LaTeX formatiga o'tkazuvchi mutaxassissiz.
            Berilgan matn ichidagi barcha matematik, fizikaviy, kimyoviy ifodalarni (darajalar, ildizlar, kasrlar, tenglamalar, grek harflari) $...$ yoki $$...$$ belgilari bilan o'rab, toza LaTeX formatida qaytaring.
            Matnning qolgan izohli qismlarini buzmang. Faqat formatlangan toza matnni chiqarib bering.
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt + f"\n\nMatn:\n{text}"],
            )
            formatted = response.text.strip()
            return JsonResponse({'status': 'success', 'formatted_text': formatted})
        except Exception as e:
            print(f"Gemini Formula Formatting Error: {str(e)}")

    return JsonResponse({'status': 'success', 'formatted_text': text})


@subadmin_permission_required('manage_schedules')
def admin_calendar_planner(request):
    groups = Group.objects.all().order_by('name')
    teachers = CustomUser.objects.filter(role='teacher').order_by('first_name')
    return render(request, 'admin_calendar_planner.html', {
        'groups': groups,
        'teachers': teachers
    })


@subadmin_permission_required('manage_schedules')
def api_calendar_schedules(request):
    schedules = Schedule.objects.select_related('group', 'teacher', 'group__subject')
    events = []
    # Map weekdays to specific dates in our mock week: Mon 2026-08-03 to Sun 2026-08-09
    day_dates = {
        'monday': '2026-08-03',
        'tuesday': '2026-08-04',
        'wednesday': '2026-08-05',
        'thursday': '2026-08-06',
        'friday': '2026-08-07',
        'saturday': '2026-08-08',
    }
    for s in schedules:
        date = day_dates.get(s.day, '2026-08-03')
        start_dt = f"{date}T{s.start_time.strftime('%H:%M:%S')}"
        end_dt = f"{date}T{s.end_time.strftime('%H:%M:%S')}"
        events.append({
            'id': s.id,
            'title': f"{s.group.name} ({s.teacher.first_name} {s.teacher.last_name[:1]}.)",
            'start': start_dt,
            'end': end_dt,
            'extendedProps': {
                'group_id': s.group_id,
                'teacher_id': s.teacher_id,
                'subject': s.group.subject.name if s.group.subject else "-",
                'day': s.day
            }
        })
    return JsonResponse(events, safe=False)


@subadmin_permission_required('manage_schedules')
@transaction.atomic
def api_update_schedule_drag(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
    
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        schedule_id = data.get('schedule_id')
        start_iso = data.get('start')  # e.g. "2026-08-05T15:00:00"
        end_iso = data.get('end')      # e.g. "2026-08-05T17:00:00"
    except Exception:
        return JsonResponse({'status': 'error', 'message': "Noto'g'ri ma'lumotlar formati."}, status=400)
        
    schedule = get_object_or_404(Schedule, id=schedule_id)
    
    # Map back dates to day names
    date_to_day = {
        '2026-08-03': 'monday',
        '2026-08-04': 'tuesday',
        '2026-08-05': 'wednesday',
        '2026-08-06': 'thursday',
        '2026-08-07': 'friday',
        '2026-08-08': 'saturday',
    }
    
    try:
        # Extract date and time strings
        start_date_str, start_time_str = start_iso.split('T')
        end_date_str, end_time_str = end_iso.split('T')
        
        day = date_to_day.get(start_date_str)
        if not day:
            return JsonResponse({'status': 'error', 'message': "Faqat Dushanba-Shanba kunlariga ko'chirish mumkin."}, status=400)
            
        start_time = parse_time(start_time_str[:5])
        end_time = parse_time(end_time_str[:5])
        
        if start_time >= end_time:
            return JsonResponse({'status': 'error', 'message': "Tugash vaqti boshlanishidan keyin bo'lishi shart."}, status=400)
            
        # Check teacher schedule conflict (ignoring current schedule)
        conflict = Schedule.objects.filter(
            teacher=schedule.teacher,
            day=day
        ).exclude(id=schedule.id).filter(
            Q(start_time__lt=end_time, end_time__gt=start_time)
        ).first()
        
        if conflict:
            return JsonResponse({
                'status': 'error', 
                'message': f"Xato: O'qituvchining ({schedule.teacher.get_full_name()}) ayni shu vaqtda ({conflict.start_time.strftime('%H:%M')} - {conflict.end_time.strftime('%H:%M')}) '{conflict.group.name}' guruhida dars jadvali mavjud!"
            }, status=400)
            
        schedule.day = day
        schedule.start_time = start_time
        schedule.end_time = end_time
        schedule.save()
        
        log_action(request.user, "Jadval surildi (Drag-and-Drop)", f"'{schedule.group.name}' guruhi darsi ({schedule.get_day_display()} {schedule.start_time.strftime('%H:%M')}) ko'chirildi.", request)
        return JsonResponse({'status': 'success', 'message': "Dars jadvali yangilandi."})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"Xatolik yuz berdi: {str(e)}"}, status=500)


@subadmin_permission_required('manage_payments')
def send_debt_reminder_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
        
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        student_id = data.get('student_id')
        msg_text = data.get('message')
    except Exception:
        return JsonResponse({'status': 'error', 'message': "Noto'g'ri ma'lumotlar formati."}, status=400)
        
    student = get_object_or_404(CustomUser, id=student_id, role='student')
    if not student.telegram_chat_id:
        return JsonResponse({'status': 'error', 'message': "Talaba botni bog'lamagan."}, status=400)
        
    from main.telegram_service import send_telegram_message
    success = send_telegram_message(student.telegram_chat_id, f"⚠️ <b>Qarzdorlik eslatmasi</b>\n\n{msg_text}")
    if success:
        log_action(request.user, "Qarzdorlik Eslatildi", f"Talaba {student.get_full_name()} ga Telegram bot orqali ogohlantirish yuborildi.", request)
        return JsonResponse({'status': 'success', 'message': "Eslatma bot orqali muvaffaqiyatli jo'natildi!"})
    else:
        return JsonResponse({'status': 'error', 'message': "Xabar yuborishda xatolik yuz berdi."}, status=500)


@subadmin_permission_required('manage_payments')
def send_telegram_test_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
        
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        student_id = data.get('student_id')
    except Exception:
        return JsonResponse({'status': 'error', 'message': "Noto'g'ri format."}, status=400)
        
    student = get_object_or_404(CustomUser, id=student_id, role='student')
    if not student.telegram_chat_id:
        return JsonResponse({'status': 'error', 'message': "Talaba Telegram botni bog'lamagan."}, status=400)
        
    from main.telegram_service import send_telegram_message
    test_msg = (
        f"🔔 <b>Test Bildirishnomasi</b>\n\n"
        f"Salom, {student.first_name} {student.last_name}!\n"
        f"Bu o'quv markazi tizimidan yuborilgan sinov xabari. Telegram ulanishingiz muvaffaqiyatli ishlayapti! 🚀"
    )
    success = send_telegram_message(student.telegram_chat_id, test_msg)
    if success:
        return JsonResponse({'status': 'success', 'message': "Test xabar bot orqali muvaffaqiyatli yuborildi!"})
    else:
        return JsonResponse({'status': 'error', 'message': "Xabarni yuborishda xatolik yuz berdi."}, status=500)


@subadmin_permission_required('manage_schedules')
def api_delete_schedule(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
    
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        schedule_id = data.get('schedule_id')
    except Exception:
        return JsonResponse({'status': 'error', 'message': "Noto'g'ri format."}, status=400)
        
    schedule = get_object_or_404(Schedule, id=schedule_id)
    group_name = schedule.group.name
    schedule.delete()
    
    return JsonResponse({
        'status': 'success',
        'message': f"{group_name} guruhi dars jadvali muvaffaqiyatli o'chirildi."
    })


@admin_required
def admin_error_logs(request):
    from main.models import SystemErrorLog
    
    current_status = request.GET.get('status', 'unresolved')
    query = request.GET.get('query', '')
    
    logs = SystemErrorLog.objects.select_related('user').order_by('-timestamp')
    
    if current_status == 'resolved':
        logs = logs.filter(is_resolved=True)
    else:
        logs = logs.filter(is_resolved=False)
        
    if query:
        logs = logs.filter(
            Q(url_path__icontains=query) |
            Q(error_message__icontains=query) |
            Q(traceback__icontains=query)
        )
        
    return render(request, 'admin_error_logs.html', {
        'logs': logs[:200],
        'query': query,
        'current_status': current_status
    })


@admin_required
def admin_resolve_error(request, log_id):
    from main.models import SystemErrorLog
    if request.method == 'POST':
        log = get_object_or_404(SystemErrorLog, id=log_id)
        log.is_resolved = True
        log.resolved_at = timezone.now()
        log.resolved_by = request.user
        log.save()
        messages.success(request, "Xatolik muvaffaqiyatli hal etildi deb belgilandi.")
    return redirect('admin_error_logs')


@admin_required
def admin_locked_pages(request):
    from main.models import LockedPage
    pages = LockedPage.objects.all().order_by('-locked_at')
    return render(request, 'admin_locked_pages.html', {
        'pages': pages
    })


@admin_required
def admin_unlock_page(request, page_id):
    from main.models import LockedPage
    if request.method == 'POST':
        page = get_object_or_404(LockedPage, id=page_id)
        page.is_active = False
        page.save()
        messages.success(request, f"'{page.url_path}' sahifasi muvaffaqiyatli blokdan ochildi.")
    return redirect('admin_locked_pages')






# ==============================================================================
# 📱 ESKIZ.UZ SMS & PHONE OTP AJAX ENDPOINTS
# ==============================================================================

@login_required
def send_phone_verification_otp_ajax(request):
    """
    Telefon raqamiga 6 xonali tasdiqlash kodini SMS orqali yuboradi va sessiyada saqlaydi.
    """
    import json
    import time

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': "Faqat POST so'rov qabul qilinadi."})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.content_type == 'application/json' else request.POST
        phone = data.get('phone_number', '').strip()
    except Exception:
        phone = request.POST.get('phone_number', '').strip()

    phone_clean = clean_phone_number(phone)
    if not phone_clean or len(phone_clean) != 12:
        return JsonResponse({'success': False, 'message': "Iltimos, to'g'ri telefon raqam kiriting (masalan: +998901234567)."})

    otp_session_key = f'phone_otp_{phone_clean}'
    last_sent_key = f'phone_otp_sent_time_{phone_clean}'
    last_sent_time = request.session.get(last_sent_key, 0)
    current_time = time.time()

    if current_time - last_sent_time < 30:
        remaining = int(30 - (current_time - last_sent_time))
        return JsonResponse({'success': False, 'message': f"Iltimos, {remaining} soniya kuting va qayta urinib ko'ring."})

    otp_code = generate_otp_code()
    request.session[otp_session_key] = {
        'otp': otp_code,
        'expires_at': current_time + 600,
        'verified': False
    }
    request.session[last_sent_key] = current_time
    request.session.modified = True

    sms_text = f"VLE Tizimi: Telefon raqamingizni tasdiqlash kodi: {otp_code}. Hech kimga bermang!"
    send_res = send_sms(phone_clean, sms_text, check_enabled=False)

    is_staff = request.user.is_superuser or getattr(request.user, 'role', '') in ['admin', 'reception']

    if send_res['success']:
        return JsonResponse({
            'success': True,
            'message': f"+{phone_clean} raqamiga 6 xonali tasdiqlash kodi yuborildi."
        })
    else:
        return JsonResponse({
            'success': True if is_staff else False,
            'message': f"Tasdiqlash kodi tayyorlandi. {send_res.get('message')}",
            'debug_code': otp_code if is_staff else None,
            'sms_error': send_res.get('message')
        })


@login_required
def verify_phone_otp_ajax(request):
    """
    Telefon raqami va kiritilgan 6 xonali OTP kodni tekshiradi.
    """
    import json
    import time

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': "Faqat POST so'rov qabul qilinadi."})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.content_type == 'application/json' else request.POST
        phone = data.get('phone_number', '').strip()
        otp = data.get('otp_code', '').strip()
    except Exception:
        phone = request.POST.get('phone_number', '').strip()
        otp = request.POST.get('otp_code', '').strip()

    phone_clean = clean_phone_number(phone)
    if not phone_clean:
        return JsonResponse({'success': False, 'message': "Telefon raqami kiritilmagan."})

    if not otp:
        return JsonResponse({'success': False, 'message': "Tasdiqlash kodi kiritilmagan."})

    otp_session_key = f'phone_otp_{phone_clean}'
    stored_data = request.session.get(otp_session_key)

    if not stored_data or not isinstance(stored_data, dict):
        return JsonResponse({'success': False, 'message': "Tasdiqlash kodi yuborilmagan yoki muddati tugagan. Qaytadan kod so'rang."})

    if time.time() > stored_data.get('expires_at', 0):
        return JsonResponse({'success': False, 'message': "Tasdiqlash kodi muddati o'tgan. Qaytadan kod so'rang."})

    if str(stored_data.get('otp')) == str(otp):
        stored_data['verified'] = True
        request.session[otp_session_key] = stored_data
        request.session[f'sms_verified_{phone_clean}'] = True
        request.session.modified = True
        return JsonResponse({'success': True, 'message': "Telefon raqami muvaffaqiyatli tasdiqlandi!"})
    else:
        return JsonResponse({'success': False, 'message': "Noto'g'ri tasdiqlash kodi kiritildi. Qaytadan tekshiring."})


@admin_required
def test_eskiz_sms_ajax(request):
    """
    Eskiz.uz SMS provayderiga ulanish va test SMS yuborish AJAX API.
    """
    import json

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': "Faqat POST so'rov qabul qilinadi."})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.content_type == 'application/json' else request.POST
        test_phone = data.get('test_phone', '').strip()
        custom_message = data.get('test_message', '').strip() or "VLE Tizimi: Eskiz.uz SMS integratsiyasi muvaffaqiyatli sinovdan o'tkazildi!"
    except Exception:
        test_phone = request.POST.get('test_phone', '').strip()
        custom_message = request.POST.get('test_message', '').strip() or "VLE Tizimi: Eskiz.uz SMS integratsiyasi muvaffaqiyatli sinovdan o'tkazildi!"

    phone_clean = clean_phone_number(test_phone)
    if not phone_clean or len(phone_clean) != 12:
        return JsonResponse({'success': False, 'message': "Iltimos, test uchun to'g'ri telefon raqam kiriting (masalan: +998901234567)."})

    res = send_sms(phone_clean, custom_message, check_enabled=False)
    balance_res = get_eskiz_balance()

    return JsonResponse({
        'success': res['success'],
        'message': res['message'],
        'balance': balance_res.get('balance', None) if balance_res.get('success') else None,
        'raw': res.get('raw')
    })


@admin_required
def get_eskiz_balance_ajax(request):
    """
    Eskiz.uz hisob balansi va ma'lumotlarini qaytaruvchi API.
    """
    bal_res = get_eskiz_balance()
    return JsonResponse(bal_res)


@subadmin_permission_required('manage_students')
def export_imported_users_pdf(request):
    """
    CSV orqali import qilingan o'quvchi va o'qituvchilarning login va yangi parollari ro'yxatini
    rasmiy, xavfsiz va chiroyli PDF hujjati shaklida yuklab olish.
    """
    imported_data = request.session.get('last_imported_users')
    if not imported_data or not imported_data.get('users'):
        messages.error(request, "Eksport qilish uchun yaqinda import qilingan foydalanuvchilar topilmadi.", extra_tags='import_error')
        return redirect('import_students_csv')

    setting = SiteSetting.objects.first()
    site_name = setting.site_name if setting and setting.site_name else "VLE Tizimi"
    role_title = "O'quvchilar" if imported_data.get('role') == 'student' else "O'qituvchilar"

    admin_user = request.user
    admin_name = f"{admin_user.first_name} {admin_user.last_name}".strip() if (admin_user.first_name or admin_user.last_name) else (admin_user.username or "Administrator")
    now_local = timezone.localtime(timezone.now())
    today_str = now_local.strftime("%d.%m.%Y %H:%M")
    doc_reg_id = f"IMP-{now_local.strftime('%y%m%d%H%M')}"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm
    )
    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_main_style = ParagraphStyle(
        'ImpMainTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=3
    )
    title_sub_style = ParagraphStyle(
        'ImpSubTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0284C7'),
        alignment=1,
        spaceAfter=10
    )
    inst_name_style = ParagraphStyle(
        'ImpInstName',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=11,
        leading=13,
        textColor=colors.HexColor('#0F172A')
    )
    inst_sub_style = ParagraphStyle(
        'ImpInstSub',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748B')
    )
    reg_style = ParagraphStyle(
        'ImpReg',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748B'),
        alignment=2
    )

    cell_style = ParagraphStyle(
        'ImpCell',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B')
    )
    cell_bold = ParagraphStyle(
        'ImpCellBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#0F172A')
    )
    cell_login = ParagraphStyle(
        'ImpCellLogin',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#0284C7')
    )
    cell_pwd = ParagraphStyle(
        'ImpCellPwd',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0D9488')
    )
    cell_center = ParagraphStyle(
        'ImpCellCenter',
        parent=styles['Normal'],
        fontName=FONT_NAME,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#475569'),
        alignment=1
    )
    cell_header = ParagraphStyle(
        'ImpCellHeader',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
        alignment=1
    )

    # 1. HEADER (Logo & Institution Info)
    logo_element = None
    if setting and setting.image and os.path.exists(setting.image.path):
        try:
            logo_element = RLImage(setting.image.path, width=20 * mm, height=20 * mm)
        except Exception:
            logo_element = None

    inst_cell = [
        Paragraph(site_name.upper(), inst_name_style),
        Spacer(1, 1 * mm),
        Paragraph("AVTOMATLASHTIRILGAN O'QUV JARAYONI VA VLE TIZIMI", inst_sub_style),
    ]

    reg_cell = [
        Paragraph(f"<b>Hujjat ID:</b> {doc_reg_id}", reg_style),
        Spacer(1, 1 * mm),
        Paragraph(f"<b>Sana:</b> {today_str}", reg_style),
        Paragraph(f"<b>Mas'ul:</b> {admin_name}", reg_style),
    ]

    if logo_element:
        header_table_data = [[logo_element, inst_cell, reg_cell]]
        header_col_widths = [24 * mm, 96 * mm, 66 * mm]
    else:
        header_table_data = [[inst_cell, reg_cell]]
        header_col_widths = [116 * mm, 70 * mm]

    header_table = Table(header_table_data, colWidths=header_col_widths)
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3 * mm))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0F172A'), spaceAfter=8))

    # 2. DOCUMENT TITLE
    elements.append(Paragraph(f"CSV ORQALI IMPORT QILINGAN {role_title.upper()}NING KIRISH MA'LUMOTLARI VA PAROLLARI", title_main_style))
    elements.append(Paragraph(f"Jami foydalanuvchilar: {imported_data.get('count', 0)} ta | SMS yuborildi: {imported_data.get('sms_sent_count', 0)} ta", title_sub_style))

    # 3. METADATA SUMMARY BAR
    meta_box_data = [
        [
            Paragraph(f"<b>Toifa:</b> {role_title}", cell_style),
            Paragraph(f"<b>Import sanasi:</b> {imported_data.get('imported_at', today_str)}", cell_style),
            Paragraph(f"<b>Jami qabul qilindi:</b> {imported_data.get('count', 0)} ta", cell_style),
            Paragraph(f"<b>Holat:</b> Muvaffaqiyatli", cell_style),
        ]
    ]
    meta_table = Table(meta_box_data, colWidths=[44 * mm, 48 * mm, 48 * mm, 46 * mm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 4 * mm))

    # 4. USERS TABLE
    table_data = [
        [
            Paragraph("№", cell_header),
            Paragraph("F.I.SH.", cell_header),
            Paragraph("LOGIN (USERNAME)", cell_header),
            Paragraph("TELEFON RAQAMI", cell_header),
            Paragraph("YARATILGAN PAROL", cell_header),
            Paragraph("SMS HOLATI", cell_header)
        ]
    ]

    for idx, u in enumerate(imported_data.get('users', []), start=1):
        sms_st = u.get('sms_status', 'Yuborilmadi')
        sms_text = "Yuborildi" if sms_st == "Yuborildi" else ("Xato" if "Xato" in sms_st else "-")
        table_data.append([
            Paragraph(str(idx), cell_center),
            Paragraph(u.get('name', '-'), cell_bold),
            Paragraph(f"@{u.get('username', '-')}", cell_login),
            Paragraph(u.get('phone', '-') or '-', cell_center),
            Paragraph(u.get('password', '-'), cell_pwd),
            Paragraph(sms_text, cell_center)
        ])

    col_widths = [10 * mm, 50 * mm, 38 * mm, 32 * mm, 32 * mm, 24 * mm]
    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]

    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            table_style_commands.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#F8FAFC')))

    main_table.setStyle(TableStyle(table_style_commands))
    elements.append(main_table)
    elements.append(Spacer(1, 6 * mm))

    # 5. FOOTER & CONFIDENTIALITY NOTICE
    notice_style = ParagraphStyle(
        'ImpNotice',
        parent=styles['Normal'],
        fontName=FONT_ITALIC,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#64748B')
    )
    elements.append(Paragraph("<b>DIQQAT:</b> Ushbu ro'yxat maxfiy hisob ma'lumotlari va parollarni o'z ichiga oladi. Hujjatni faqat vakolatli xodimlar saqlashi va begona shaxslarga bermasligi shart.", notice_style))
    elements.append(Spacer(1, 4 * mm))

    sign_data = [
        [
            Paragraph(f"<b>Mas'ul admin:</b> {admin_name}", cell_style),
            Paragraph("<b>Imzo:</b> ___________________", cell_center),
            Paragraph(f"<b>Tasdiqlangan sana:</b> {today_str}", cell_style)
        ]
    ]
    sign_table = Table(sign_data, colWidths=[66 * mm, 60 * mm, 60 * mm])
    sign_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(KeepTogether(sign_table))

    doc.build(elements)
    buffer.seek(0)

    filename = f"import_parollar_{imported_data.get('role', 'users')}_{now_local.strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
