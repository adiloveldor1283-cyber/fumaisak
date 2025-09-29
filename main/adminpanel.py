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
    GroupStudentMembership, GroupPaymentInfo, StudentPayment, SiteSetting
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse, HttpResponseBadRequest
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from django.utils.dateparse import parse_time
from django.http import HttpResponseForbidden
from django.utils.dateparse import parse_datetime
from django.utils.html import escape




#Guruh uchun
@login_required
def all_groups_admin(request):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    groups = Group.objects.all().order_by('-created_at')
    return render(request, 'all_groups_admin.html', {'groups': groups})


@login_required
def edit_group_admin(request, group_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    group = get_object_or_404(Group, id=group_id)

    all_teachers = CustomUser.objects.filter(role='teacher').exclude(id__in=group.teachers.all())
    all_students = CustomUser.objects.filter(role='student').exclude(id__in=group.students.all())

    if request.method == 'POST':
        if 'delete' in request.POST:
            group.delete()
            messages.success(request, "Guruh muvaffaqiyatli o‘chirildi.", extra_tags='edit_group')
            return redirect('all_groups_admin')

        group.name = request.POST.get('group-name')
        date_str = request.POST.get('date') + ' ' + request.POST.get('time')  # '2025-06-28 13:15'
        naive_datetime = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        aware_datetime = make_aware(naive_datetime)

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

            for student_id in students_to_add:
                student = CustomUser.objects.get(id=student_id)
                GroupStudentMembership.objects.create(group=group, student=student)

            GroupStudentMembership.objects.filter(group=group, student_id__in=students_to_remove).delete()

        messages.success(request, "Guruh muvaffaqiyatli saqlandi.", extra_tags='edit_group')
        return redirect('all_groups_admin')

    context = {
        'group': group,
        'all_teachers': all_teachers,
        'all_students': all_students,
    }
    return render(request, 'edit_group_admin.html', context)

@login_required
def create_group_admin(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    all_teachers = CustomUser.objects.filter(role='teacher')
    all_students = CustomUser.objects.filter(role='student')

    if request.method == 'POST':
        name = request.POST.get('group-name')
        datetime_str = f"{request.POST.get('date')} {request.POST.get('time')}"
        naive_dt = parse_datetime(datetime_str)

        # Agar timezone aktiv bo‘lsa va datetime naive bo‘lsa — make_aware qilamiz
        created_at = make_aware(naive_dt) if naive_dt else timezone.now()

        selected_teacher_ids = request.POST.getlist('selected_teachers')
        selected_student_ids = request.POST.getlist('selected_students')

        group = Group.objects.create(name=name, created_at=created_at)
        group.teachers.set(CustomUser.objects.filter(id__in=selected_teacher_ids))
        for student_id in selected_student_ids:
            student = CustomUser.objects.get(id=student_id)
            GroupStudentMembership.objects.create(group=group, student=student)

        messages.success(request, "Yangi guruh muvaffaqiyatli yaratildi.", extra_tags='yangi_guruh')
        return redirect('all_groups_admin')

    context = {
        'all_teachers': all_teachers,
        'all_students': all_students,
        'timezone': timezone,
    }
    return render(request, 'group_create_admin.html', context)

#Sudent uchun
@login_required
def students_list_admin(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_users')
        if selected_ids:
            deleted_count = CustomUser.objects.filter(id__in=selected_ids, role='student').delete()[0]
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

@login_required
def add_student(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone_number = request.POST.get('phone_number')
        password = request.POST.get('password')
        confirm = request.POST.get('confirm_password')
        role = request.POST.get('role')
        is_active = request.POST.get('is_active') == 'on'
        profile_image = request.FILES.get('profile_image')

        if not all([username, password, confirm, role, first_name, last_name, phone_number]):
            messages.error(request, "Barcha maydonlar to‘ldirilishi kerak.", extra_tags='password_creat')
            return redirect('add_student')

        if password != confirm:
            messages.error(request, "Parollar mos emas.", extra_tags='password_creat')
            return redirect('add_student')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud.", extra_tags='password_creat')
            return redirect('add_student')

        user = CustomUser.objects.create(
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            password=make_password(password),
            role=role,
            is_active=is_active,

        )
        if profile_image:
            user.profile_image = profile_image
            user.save()

        messages.success(request, "Foydalanuvchi muvaffaqiyatli qo‘shildi.", extra_tags='edit_user')
        return redirect('students_list_admin')

    return render(request, 'add-student.html')


@login_required
def edit_student(request, student_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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
            student.profile_image = request.FILES['profile_image']

        student.save()
        messages.success(request, "O'quvchi ma'lumotlari saqlandi.", extra_tags='edit_user')
        return redirect('students_list_admin')

    return render(request, 'student-tahrirlash.html', {'student': student})

#O'qituvchilar uchun
@login_required
def teachers_list_admin(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_users')
        if selected_ids:
            deleted_count = CustomUser.objects.filter(id__in=selected_ids, role='teacher').delete()[0]
            messages.success(request, f"{deleted_count} ta o‘qituvchi muvaffaqiyatli o‘chirildi.", extra_tags='teacher_list')
        else:
            messages.warning(request, "Hech qanday o‘qituvchi tanlanmadi.", extra_tags='teacher_list')
        return redirect('teachers_list_admin')

    # GET so‘rov bo‘lsa - ro‘yxatni qaytaradi
    teachers = CustomUser.objects.filter(role='teacher')
    total_teachers = teachers.count()
    active_teachers = teachers.filter(is_active=True).count()
    inactive_teachers = teachers.filter(is_active=False).count()

    return render(request, 'teachers-list-admin.html', {
        'teachers': teachers,
        'total_teachers': total_teachers,
        'active_teachers': active_teachers,
        'inactive_teachers': inactive_teachers,
    })

@login_required
def edit_teacher(request, teacher_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    teacher = get_object_or_404(CustomUser, id=teacher_id)

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
            teacher.image = request.FILES['profile_image']

        teacher.save()
        messages.success(request, "O'qituvchi ma'lumotlari saqlandi.", extra_tags='teacher_list')
        return redirect('teachers_list_admin')

    return render(request, 'teacher-tahrirlash.html', {'teacher': teacher})

@login_required
def add_teacher(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    if request.method == 'POST':
        username = request.POST.get('teacher_username')
        first_name = request.POST.get('teacher_first_name')
        last_name = request.POST.get('teacher_last_name')
        phone_number = request.POST.get('teacher_phone_number')
        password = request.POST.get('password')
        confirm = request.POST.get('confirm_password')
        role = request.POST.get('role')
        is_active = request.POST.get('is_active') == 'on'
        profile_image = request.FILES.get('profile_image')

        if not all([username, password, confirm, role, first_name, last_name, phone_number]):
            messages.error(request, "Barcha maydonlar to‘ldirilishi kerak.", extra_tags='password_creat_teacher')
            return redirect('add_teacher')

        if password != confirm:
            messages.error(request, "Parollar mos emas.", extra_tags='password_creat_teacher')
            return redirect('add_teacher')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud.", extra_tags='password_creat_teacher')
            return redirect('add_teacher')

        CustomUser.objects.create(
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            password=make_password(password),
            role=role,
            is_active=is_active,
            profile_image=profile_image
        )
        messages.success(request, "O'qituvchi muvaffaqiyatli qo‘shildi.", extra_tags='teacher_list')
        return redirect('add_teacher')

    return render(request, 'add-teacher.html')

@login_required
def admin_password(request):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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

def reset_student_password(request, student_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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

def reset_teacher_password(request, teacher_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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

def export_students_pdf(request):
    group_id = request.GET.get('group_id')

    # 1. O‘quvchilarni olish
    if group_id == "all" or not group_id:
        students = CustomUser.objects.filter(role='student').order_by('last_name')
        group_name = "Umumiy o‘quvchilar ro‘yxati"
        teacher_list = []
        created_at = None
    else:
        try:
            group = Group.objects.get(id=group_id)
            students = group.students.all().order_by('last_name')
            group_name = f"{group.name} guruhining o'quvchilari ro'yhati"
            teacher_list = group.teachers.all()
            created_at = group.created_at
        except Group.DoesNotExist:
            return HttpResponse("Guruh topilmadi", status=404)

    # 2. PDF hujjatni tayyorlash
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # 3. Sarlavha (yuqori qism)
    title = Paragraph(f"<b>{group_name}</b>", styles['Title'])
    sana_paragraph = Paragraph(f"<i>Sana: {today}</i>", styles['Normal'])

    elements.append(title)
    elements.append(sana_paragraph)
    elements.append(Spacer(1, 12))  # Bosh joy

    # 4. Jadval ma'lumotlari
    data = [["No", "Familiyasi", "Ismi", "Holati", "Telefon raqami"]]
    for index, student in enumerate(students, start=1):
        data.append([
            str(index),
            student.last_name,
            student.first_name,
            student.get_role_display(),
            student.phone_number or "-"
        ])

    table = Table(data, colWidths=[40, 120, 120, 100, 130])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ]))
    elements.append(table)

    # 5. Jadval ostiga o‘qituvchilar va vaqt
    if group_id != "all":
        elements.append(Spacer(1, 24))
        if teacher_list:
            teachers_names = ", ".join(f"{t.first_name} {t.last_name}" for t in teacher_list)
        else:
            teachers_names = "Biriktirilmagan"

        elements.append(Paragraph(f"<b>O‘qituvchi(lar):</b> {teachers_names}", styles['Normal']))

        if created_at:
            created_str = created_at.strftime("%Y-%m-%d %H:%M")
            elements.append(Paragraph(f"<b>Guruh ochilgan vaqti:</b> {created_str}", styles['Normal']))

    # 6. PDF ni yaratish va jo‘natish
    doc.build(elements)
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')




DAYS_ORDER = [day[0] for day in DAYS_OF_WEEK]
DAY_NAMES = dict(DAYS_OF_WEEK)

@login_required
def edit_group_teacher_schedule(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    teachers = group.teachers.all()
    days = DAYS_OF_WEEK

    if request.method == 'POST':
        # Avval eski darslarni o‘chirib tashlaymiz
        Schedule.objects.filter(group=group, teacher__in=teachers).delete()

        for teacher in teachers:
            for day_value, _ in days:
                # Shu o‘qituvchi va kun uchun kelgan inputlarni ajratib olamiz
                input_values = request.POST.getlist(f"schedule-{teacher.id}-{day_value}")
                for time_str in input_values:
                    time_str = time_str.strip()
                    if time_str:
                        try:
                            start_str, end_str = [s.strip() for s in time_str.split('-')]
                            start_time = timezone.datetime.strptime(start_str, "%H:%M").time()
                            end_time = timezone.datetime.strptime(end_str, "%H:%M").time()

                            Schedule.objects.create(
                                group=group,
                                teacher=teacher,
                                day=day_value,
                                start_time=start_time,
                                end_time=end_time
                            )
                        except ValueError:
                            continue  # noto‘g‘ri formatni tashlab ketadi

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



@login_required
def all_group_schedules_view(request):
    groups = Group.objects.all()
    schedules = Schedule.objects.select_related('group').order_by('group', 'day', 'start_time')

    # Har bir group uchun jadvalni ajratib olish
    group_schedules = {}
    for schedule in schedules:
        group = schedule.group
        if group not in group_schedules:
            group_schedules[group] = []
        group_schedules[group].append(schedule)

    return render(request, 'all_group_schedules.html', {
        'group_schedules': group_schedules,
    })



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


@login_required
def add_topshiriq(request):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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

        group = Group.objects.get(id=group_id)
        teacher = CustomUser.objects.get(id=teacher_id)

        Assignment.objects.create(
            title=title,
            group=group,
            teacher=teacher,
            deadline=deadline,
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


@login_required
def admin_assignment_list(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    assignments = Assignment.objects.all().order_by('-created_at')
    return render(request, 'admin-topshiriq-list.html', {'assignments': assignments})


def edit_topshiriq(request, assignment_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id)

    if request.method == 'POST':

        if not all([request.POST.get('title'),
                    request.POST.get('group_id'),
                    request.POST.get('teacher_id'),
                    request.POST.get('deadline'),
                    request.POST.get('max_score')]):
            messages.error(request, "Hamma maydonlarni to‘ldiring!")
            return redirect('edit_topshiriq')

        assignment.title = request.POST.get('title')
        assignment.group = Group.objects.get(id=request.POST.get('group_id'))
        assignment.teacher = CustomUser.objects.get(id=request.POST.get('teacher_id'))
        assignment.deadline = parse_datetime(request.POST.get('deadline'))
        assignment.max_score = request.POST.get('max_score')

        if 'file' in request.FILES:
            # ✅ Eski faylni o‘chirish
            if assignment.file:
                old_file_path = assignment.file.path
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            # ✅ Yangi faylni saqlash
            assignment.file = request.FILES['file']

        assignment.save()
        return redirect('admin_assignment_list')

    groups = Group.objects.all()
    teachers = CustomUser.objects.filter(role='teacher')

    return render(request, 'edit-topshiriq-admin.html', {
        'assignment': assignment,
        'groups': groups,
        'teachers': teachers
    })

@login_required
def admin_delete_assignment(request, assignment_id):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id)

    # Faylni diskdan o‘chirish
    if assignment.file:
        file_path = assignment.file.path
        if os.path.exists(file_path):
            os.remove(file_path)

    assignment.delete()
    messages.success(request, "Topshiriq muvaffaqiyatli o‘chirildi.")
    return redirect('admin_assignment_list')


@login_required
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

        # Javoblarni qabul qilish (kiritilgan inputlar sonini bilmasligimiz sababli)
        index = 0
        while True:
            answer_text = request.POST.get(f'answer_text_{index}')
            is_correct = request.POST.get(f'is_correct_{index}') == 'on'

            if not answer_text:
                break  # Javob tugadi

            Answer.objects.create(
                question=question,
                text=answer_text,
                is_correct=is_correct
            )
            index += 1

        return redirect('question_list')

        # GET bo‘lsa — forma ko‘rsatamiz
    quizzes = Quiz.objects.all()
    return render(request, 'add-test-admin.html', {'quizzes': quizzes})


@login_required
def question_list(request):
    user = request.user

    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    questions = Question.objects.all()

    return render(request, 'admin-test-list.html', {'questions': questions})

@login_required
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

        # Yangi javoblar qo‘shish (max 10 ta)
        for i in range(10):
            text = request.POST.get(f"new_answer_text_{i}")
            is_correct = request.POST.get(f"new_is_correct_{i}") == 'on'
            if text:
                Answer.objects.create(
                    question=question,
                    text=text,
                    is_correct=is_correct
                )

        return redirect('question_list')

    answers = question.answers.all()
    all_quizzes = Quiz.objects.all()

    return render(request, 'edit-test.html', {
        'question': question,
        'answers': answers,
        'all_quizzes': all_quizzes,
    })

@login_required
def delete_question(request, pk):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    question = get_object_or_404(Question, pk=pk)

    if request.method == 'POST':
        question.delete()
        return redirect('question_list')  # o‘chirilgach qayta yuklash

    return HttpResponseForbidden("Noto‘g‘ri so‘rov")


@login_required
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


@login_required
def quiz_list(request):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    quizzes = Quiz.objects.select_related('group', 'teacher').all().order_by('-created_at')
    return render(request, 'quiz-list-admin.html', {'quizzes': quizzes})


@login_required
def edit_quiz(request, quiz_id):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

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

@login_required
def delete_quiz(request, quiz_id):
    user = request.user
    if not (user.is_superuser or user.is_staff or user.role == 'admin'):
        return redirect('login')

    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.delete()
    messages.success(request, "Quiz muvaffaqiyatli o‘chirildi.")
    return redirect('quiz_list')


@login_required
@require_http_methods(["GET", "POST"])
def import_students_csv(request):
    if request.method == "POST":
        role = request.POST.get("role")  # student yoki teacher

        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Iltimos, CSV fayl tanlang.", extra_tags='import_error')
            return redirect("import_students_csv")

        if not csv_file.name.endswith(".csv"):
            messages.error(request, "Faqat .csv fayl yuklashingiz mumkin!", extra_tags='import_error')
            return redirect("import_students_csv")

        try:
            data_set = csv_file.read().decode("utf-8-sig")
            io_string = io.StringIO(data_set)
            reader = csv.reader(io_string)

            headers = next(reader)
            headers = [h.strip().lower() for h in headers]

            expected_headers = ["username", "first_name", "last_name", "phone_number", "password"]
            if headers != expected_headers:
                messages.error(request, f"CSV ustunlari noto‘g‘ri! Kerakli format: {', '.join(expected_headers)}",
                               extra_tags='import_error')
                return redirect("import_students_csv")

            count = 0
            for row in reader:
                if len(row) != 5:
                    continue

                username, first_name, last_name, phone_number, password = [x.strip() for x in row]

                if not username or not phone_number or not password:
                    continue

                if not CustomUser.objects.filter(username=username).exists():
                    user = CustomUser(
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        phone_number=phone_number,
                        role=role  # HTML'dan kelgan qiymat
                    )
                    user.set_password(password)
                    user.save()
                    count += 1

            messages.success(request, f"{count} ta { 'talaba' if role == 'student' else 'o‘qituvchi' } muvaffaqiyatli qo‘shildi!",
                             extra_tags='import_success')
        except Exception as e:
            messages.error(request, f"Xatolik: {e}", extra_tags='import_error')

        return redirect("import_students_csv")

    return render(request, "import_students.html")

@login_required
def group_payment_list(request):
    groups = Group.objects.filter(payment_info__isnull=False).select_related("payment_info")
    return render(request, "group-payments-list.html", {"groups": groups})


@login_required
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
def group_students(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    students = group.students.all()
    months = [m[0] for m in StudentPayment.MONTH_CHOICES]
    return render(request, "admin_group_students.html", {"group": group, "students": students, "months": months,})

# O‘quvchi uchun to‘lov kiritish
def student_payment(request, group_id, student_id):
    group = get_object_or_404(Group, id=group_id)
    student = get_object_or_404(CustomUser, id=student_id, role="student")
    payment_info = get_object_or_404(GroupPaymentInfo, group=group)

    if request.method == "POST":
        month = request.POST.get("month")
        amount_paid = request.POST.get("amount_paid")

        if not month or not amount_paid:
            messages.error(request, "Barcha maydonlarni to‘ldiring!", extra_tags='import_success')
            return redirect("student_payment", group_id=group.id, student_id=student.id)

        # To‘lov yozuvini yaratamiz va saqlaymiz
        payment = StudentPayment.objects.create(
            student=student,
            group=group,
            month=month,
            amount_paid=amount_paid,
        )

        # PDF linkni yaratamiz
        pdf_url = reverse("payment_receipt", args=[payment.id])

        # Foydalanuvchiga xabar va yuklab olish linki
        messages.success(
            request,
            f"{student.get_full_name()} uchun to‘lov saqlandi! "
            f"<a href='{pdf_url}' target='_blank'>PDF yuklab olish</a>",
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


@login_required
def student_list(request):
    students = CustomUser.objects.filter(role="student")
    return render(request, "admin_student_list.html", {"students": students})


@login_required
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

def payment_receipt(request, payment_id):
    payment = get_object_or_404(StudentPayment, id=payment_id)

    # Tasdiqlash kodi
    unique_str = f"{payment.id}{payment.student.id}{payment.amount_paid}{payment.month}"
    verify_code = hashlib.sha256(unique_str.encode()).hexdigest()[:12]
    verify_url = request.build_absolute_uri(f"/payment/verify/{payment.id}/{verify_code}")

    # Kvitansiya raqami
    inv_number = f"INV-{payment.paid_at.year}-{payment.id:04d}"

    # PDF response
    response = HttpResponse(content_type='application/pdf')
    filename = f"tolov_{payment.student.last_name}_{payment.month}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    # Sarlavha
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, height - 20*mm, "Kurs uchun to‘lov hujjati")
    p.line(20 * mm, height - 22 * mm, width - 20 * mm, height - 22 * mm)

    # Jadval ma'lumotlari
    data = [
        ["Kvitansiya raqami:", inv_number],
        ["O‘quvchi Ism Familiyasi:", f"{payment.student.first_name} {payment.student.last_name}"],
        ["Qaysi guruh uchun:", payment.group.name],
        ["Qaysi oy uchun:", payment.month],
        ["To‘lanishi kerak bo‘lgan summa:", f"{payment.group.payment_info.monthly_fee} so‘m"],
        ["To‘lov summasi:", f"{payment.amount_paid:,.2f} so‘m"],
        ["To‘lov qilgan vaqt:", timezone.localtime(payment.paid_at).strftime("%Y-%m-%d %H:%M")],
        ["To‘lov ID:", str(payment.id)],
    ]
    table = Table(data, colWidths=[80*mm, 95*mm])
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))

    # Jadval joylashuvi (sarlavhadan 5 mm past)
    table_height = len(data) * 7*mm
    table_y = height - 20*mm - 5*mm - table_height
    table.wrapOn(p, width, height)
    table.drawOn(p, 20*mm, table_y)

    # QR kod tayyorlash (35×35 mm)
    qr_img = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_image = ImageReader(qr_buffer)
    qr_x = width - 50*mm
    qr_y = table_y - 35*mm
    p.drawImage(qr_image, qr_x, qr_y, 33*mm, 33*mm)

    # “Tasdiqlovchi QR kod” matni (kichik shrift)
    p.setFont("Helvetica", 8)
    p.drawCentredString(qr_x + 15*mm, qr_y - 5*mm, "Tasdiqlovchi QR kod:")

    # Imzo va sana (QR kod bilan bir balandlikda chapda)
    p.setFont("Helvetica", 12)
    p.drawString(20*mm, qr_y + 15*mm, "Imzo: __________")
    p.drawString(20*mm, qr_y + 22*mm, f"Sana: {datetime.now().strftime('%d.%m.%Y')}")

    site_settings = SiteSetting.objects.first()
    if site_settings and site_settings.image:
        circle_img_buf = make_circle_image(site_settings.image.path, size_px=120)
        logo_img = ImageReader(circle_img_buf)
        p.drawImage(logo_img, 60 * mm, qr_y + 2 * mm, 25 * mm, 25 * mm, mask='auto')

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
        return payment_receipt(request, payment.id)
    else:
        return HttpResponse("Bu hujjat bazada mavjud emas")

def student_payment_pdf(request, student_id):
    student = get_object_or_404(CustomUser, id=student_id, role='student')

    # O‘quvchining barcha to‘lovlari
    payments = StudentPayment.objects.filter(student=student).select_related("group").order_by("paid_at")

    # HTTP javob PDF sifatida
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{student.username}_payments.pdf"'

    # PDF hujjat
    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"To‘lov ma’lumotlari: {student.first_name} {student.last_name}", styles['Heading1']))
    elements.append(Spacer(1, 12))

    # Jadval sarlavhalari
    data = [["Guruh", "Oy", "Kurs davomiyligi", "To‘lash kerak", "To‘langan summa", "To‘langan vaqti"]]

    for p in payments:
        try:
            group_info = GroupPaymentInfo.objects.get(group=p.group)
            course_duration = f"{group_info.course_duration_months} oy"
            monthly_fee = f"{group_info.monthly_fee} so‘m"
        except GroupPaymentInfo.DoesNotExist:
            course_duration = "-"
            monthly_fee = "-"

        data.append([
            p.group.name,
            p.month,
            course_duration,
            monthly_fee,
            f"{p.amount_paid} so‘m",
            p.paid_at.strftime("%Y-%m-%d %H:%M"),
        ])

    # Jadval
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
    ]))

    elements.append(table)
    doc.build(elements)

    return response
