from datetime import timedelta
from functools import wraps

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.db.models import Count, Sum

from . import student
from .models import Group, CustomUser, Schedule, Quiz, Question, Answer, StudentQuizResult, Assignment, Attendance, \
    AssignmentSubmission, GroupStudentMembership, GroupLesson, GroupVideo, Subject, SubjectMaterial, Book
from .utils import log_action

import os
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

# =====================================================================
# MAXSUS DEKORATOR: Faqat o'qituvchi roliga ruxsat beradi
# =====================================================================
def teacher_required(view_func):
    """@login_required + role='teacher' tekshiruvini birlashtirgan dekorator."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'teacher':
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


# =====================================================================
# UMUMIY YORDAMCHI: Davomat topshirish shartlarini tekshirish
# =====================================================================
def check_attendance_eligibility(teacher, group):
    """
    Davomat topshirish mumkinligini tekshiradi.
    Qaytaradi: (allowed: bool, error_message: str | None)
    """
    today = timezone.localdate()
    days_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday',
                3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
    today_day = days_map[timezone.localtime().weekday()]

    schedule = Schedule.objects.filter(group=group, day=today_day).first()
    if not schedule:
        return False, "Bugun bu guruhda dars yo'q!"

    now_time = timezone.localtime().time()
    if not (schedule.start_time <= now_time <= schedule.end_time):
        return False, (f"Faqat dars vaqtida davomat topshirish mumkin! "
                       f"Dars vaqti: {schedule.start_time.strftime('%H:%M')} - "
                       f"{schedule.end_time.strftime('%H:%M')}")

    already_submitted = Attendance.objects.filter(
        teacher=teacher, group=group, date=today
    ).exists()
    if already_submitted:
        return False, "Siz bu dars uchun davomat topshirib bo'lgansiz!"

    return True, None


# O'qituvchiga tegishli guruhlardagi o'quvchilarni olish
def get_teacher_students(teacher):
    groups = teacher.teachers_groups.all()
    return CustomUser.objects.filter(student_groups__in=groups, role='student').distinct()

# Talabalarni kategoriyalash – faollikka qarab

def categorize_students(teacher, students=None, quizzes=None, assignments=None, membership_dict=None, quiz_results_dict=None, submissions_dict=None):
    if students is None:
        students = get_teacher_students(teacher)
    if quizzes is None:
        quizzes = Quiz.objects.filter(teacher=teacher)
    if assignments is None:
        assignments = Assignment.objects.filter(teacher=teacher)

    if membership_dict is None:
        teacher_groups = teacher.teachers_groups.all()
        memberships = GroupStudentMembership.objects.filter(student__in=students, group__in=teacher_groups).values('student_id', 'group_id', 'joined_at')
        membership_dict = {(m['student_id'], m['group_id']): m['joined_at'] for m in memberships}

    if quiz_results_dict is None:
        quiz_results = StudentQuizResult.objects.filter(student__in=students, quiz__in=quizzes).values('student_id', 'quiz_id', 'score')
        quiz_results_dict = {(r['student_id'], r['quiz_id']): r['score'] for r in quiz_results}

    if submissions_dict is None:
        submissions = AssignmentSubmission.objects.filter(student__in=students, assignment__in=assignments, grade__isnull=False).values('student_id', 'assignment_id', 'grade')
        submissions_dict = {(s['student_id'], s['assignment_id']): s['grade'] for s in submissions}

    good, average, weak = [], [], []
    student_levels = {}

    for student in students:
        quiz_score_sum = 0
        assign_score_sum = 0
        student_total_max = 0

        for quiz in quizzes:
            joined_at = membership_dict.get((student.id, quiz.group_id))
            if joined_at and joined_at <= quiz.created_at:
                score = quiz_results_dict.get((student.id, quiz.id))
                if score is not None:
                    quiz_score_sum += score
                student_total_max += quiz.max_score

        for assignment in assignments:
            joined_at = membership_dict.get((student.id, assignment.group_id))
            if joined_at and joined_at <= assignment.created_at:
                grade = submissions_dict.get((student.id, assignment.id))
                if grade is not None:
                    assign_score_sum += grade
                student_total_max += assignment.max_score

        if student_total_max == 0:
            student_levels[student.id] = "Yangi o'quvchi"
            continue

        total_score = quiz_score_sum + assign_score_sum
        score_percent = (total_score / student_total_max) * 100

        if score_percent >= 90:
            good.append(student)
            student_levels[student.id] = "Yuqori daraja"
        elif score_percent >= 60:
            average.append(student)
            student_levels[student.id] = "O'rtacha daraja"
        else:
            weak.append(student)
            student_levels[student.id] = "Boshlang'ich daraja"

    # students.count() o'rniga len() ishlatamiz — qo'shimcha DB so'rovini oldini oladi
    total = students if isinstance(students, int) else len(list(students)) if hasattr(students, '__len__') else students.count()
    return {
        'total': len(good) + len(average) + len(weak),
        'good': good,
        'average': average,
        'weak': weak,
        'student_levels': student_levels
    }


@teacher_required
def teacher_home_view(request):
    teacher = request.user

    # Get initial objects
    students = get_teacher_students(teacher)
    teacher_quizzes = Quiz.objects.filter(teacher=teacher)
    teacher_assignments = Assignment.objects.filter(teacher=teacher)

    # 1. Fetch memberships using .values() to prevent Django model instantiation overhead
    teacher_groups = teacher.teachers_groups.all()
    memberships = GroupStudentMembership.objects.filter(student__in=students, group__in=teacher_groups).values('student_id', 'group_id', 'joined_at')
    membership_dict = {(m['student_id'], m['group_id']): m['joined_at'] for m in memberships}

    # 2. Fetch quiz results for score sum using .values()
    quiz_results = StudentQuizResult.objects.filter(student__in=students, quiz__in=teacher_quizzes).values('student_id', 'quiz_id', 'score')
    quiz_results_dict = {(r['student_id'], r['quiz_id']): r['score'] for r in quiz_results}

    # 3. Fetch submissions with grade for score sum using .values()
    submissions = AssignmentSubmission.objects.filter(student__in=students, assignment__in=teacher_assignments, grade__isnull=False).values('student_id', 'assignment_id', 'grade')
    submissions_dict = {(s['student_id'], s['assignment_id']): s['grade'] for s in submissions}

    # 4. Fetch all submissions (including ungraded) to count completions
    all_submissions = AssignmentSubmission.objects.filter(student__in=students, assignment__in=teacher_assignments).values_list('student_id', 'assignment_id')
    all_submissions_set = set(all_submissions)

    # 5. Fetch all quiz results to count completions
    all_quiz_results = StudentQuizResult.objects.filter(student__in=students, quiz__in=teacher_quizzes).values_list('student_id', 'quiz_id')
    all_quiz_results_set = set(all_quiz_results)

    # Categorize students using the pre-fetched data
    stats = categorize_students(
        teacher,
        students=students,
        quizzes=teacher_quizzes,
        assignments=teacher_assignments,
        membership_dict=membership_dict,
        quiz_results_dict=quiz_results_dict,
        submissions_dict=submissions_dict
    )

    # Bosqich 3 optimallashtirish: O(N*M) nested looplarni samarali hisoblash bilan almashtirish.
    # student_ids ni set ga olamiz — tez lookup uchun
    student_ids = set(s.id for s in students)

    completed_assignments = 0
    total_assignment_opportunities = 0
    for assignment in teacher_assignments:
        # Bu topshiriqqa qarashli studentlar (membership bo'yicha)
        eligible = [
            sid for sid in student_ids
            if membership_dict.get((sid, assignment.group_id)) and
               membership_dict[(sid, assignment.group_id)] <= assignment.created_at
        ]
        total_assignment_opportunities += len(eligible)
        completed_assignments += sum(
            1 for sid in eligible if (sid, assignment.id) in all_submissions_set
        )

    completed_quizzes = 0
    total_quiz_opportunities = 0
    for quiz in teacher_quizzes:
        # Bu quizga qarashli studentlar (membership bo'yicha)
        eligible = [
            sid for sid in student_ids
            if membership_dict.get((sid, quiz.group_id)) and
               membership_dict[(sid, quiz.group_id)] <= quiz.created_at
        ]
        total_quiz_opportunities += len(eligible)
        completed_quizzes += sum(
            1 for sid in eligible if (sid, quiz.id) in all_quiz_results_set
        )

    # Foizlarni hisoblash
    assignment_completion_percent = (
        (completed_assignments / total_assignment_opportunities) * 100
        if total_assignment_opportunities > 0 else 0
    )
    quiz_completion_percent = (
        (completed_quizzes / total_quiz_opportunities) * 100
        if total_quiz_opportunities > 0 else 0
    )

    # Warning students list - Low grades and/or low attendance (<70%)
    low_att_reasons = {}
    attendance_stats = Attendance.objects.filter(
        student__in=students,
        group__in=teacher_groups
    ).values('student_id', 'group_id').annotate(
        total=Count('id'),
        present=Count('id', filter=models.Q(status='present'))
    )
    for stat in attendance_stats:
        total = stat['total']
        present = stat['present']
        rate = (present / total * 100) if total > 0 else 100
        if rate < 70:
            sid = stat['student_id']
            gid = stat['group_id']
            group_name = next((g.name for g in teacher_groups if g.id == gid), "Guruh")
            if sid not in low_att_reasons:
                low_att_reasons[sid] = []
            low_att_reasons[sid].append(f"Davomati past: {group_name} ({round(rate, 1)}%)")

    student_groups_qs = Group.objects.filter(teachers=teacher, students__in=students).prefetch_related('students')
    student_groups_map = {}
    for g in student_groups_qs:
        for s in g.students.all():
            if s.id not in student_groups_map:
                student_groups_map[s.id] = []
            if g.name not in student_groups_map[s.id]:
                student_groups_map[s.id].append(g.name)

    warning_students_list = []
    for student in students:
        reasons = []
        if student in stats['weak']:
            reasons.append("O'zlashtirish ko'rsatkichi past (60% dan kam)")
        if student.id in low_att_reasons:
            reasons.extend(low_att_reasons[student.id])

        if reasons:
            grps = student_groups_map.get(student.id, [])
            groups_str = ", ".join(grps)
            warning_students_list.append({
                'student': student,
                'groups': groups_str,
                'reasons': reasons
            })

    distinct_students = CustomUser.objects.filter(student_groups__in=teacher_groups).distinct()

    context = {
        'teacher': teacher,
        'students': distinct_students,
        'warning_students': warning_students_list,
        'total_students': stats['total'],
        'good_students_count': len(stats['good']),
        'average_students_count': len(stats['average']),
        'weak_students_count': len(stats['weak']),
        'assignment_completion_percent': round(assignment_completion_percent, 1),
        'assignment_missing_percent': round(100 - assignment_completion_percent, 1),
        'quiz_completion_percent': round(quiz_completion_percent, 1),
        'quiz_missing_percent': round(100 - quiz_completion_percent, 1),
        'student_levels': stats['student_levels'],
        'has_assignments': teacher_assignments.exists(),
        'has_quizzes': teacher_quizzes.exists(),
    }
    return render(request, 'teacher_home.html', context)


@teacher_required
def teacher_profile_view(request):
    teacher = request.user

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'change_password':
            old_password = request.POST.get('old_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')

            if not teacher.check_password(old_password):
                messages.error(request, "Eski parol noto‘g‘ri!", extra_tags='password')
            elif new_password1 != new_password2:
                messages.error(request, "Yangi parollar bir xil emas!", extra_tags='password')
            elif len(new_password1) < 8:
                messages.error(request, "Yangi parol kamida 8 ta belgidan iborat bo‘lishi kerak!", extra_tags='password')
            else:
                teacher.set_password(new_password1)
                teacher.save()
                update_session_auth_hash(request, teacher)
                messages.success(request, "Parolingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='password_img')

        elif form_type == 'upload_image':
            if 'profile_image' in request.FILES:
                image = request.FILES['profile_image']
                from main.validators import validate_image_file
                from django.core.exceptions import ValidationError
                try:
                    validate_image_file(image)
                except ValidationError as ve:
                    messages.error(request, ve.message, extra_tags='password')
                    return redirect('teacher_profile')
                teacher.profile_image = image
                teacher.save()
                messages.success(request, "Rasmingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='password_img')
            else:
                messages.error(request, "Rasm tanlanmadi.", extra_tags='password')

    return render(request, 'teacher-profile.html', {'teacher': teacher,})

@teacher_required
def my_student_view(request):
    teacher = request.user

    teacher_groups = Group.objects.filter(teachers=teacher)

    students = CustomUser.objects.filter(student_groups__in=teacher_groups).distinct()

    context = {'students': students, 'teacher': teacher,}
    return render(request, 'teacher_students_list.html', context)

@teacher_required
def my_groups_view(request):
    teacher = request.user

    groups = teacher.teachers_groups.all()

    return render(request, 'teacher_group_list.html', {'groups': groups, 'teacher': teacher,})

@teacher_required
def group_detail_view(request, group_id):
    teacher = request.user

    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    # Dars yozish (POST)
    if request.method == 'POST' and request.POST.get('action') == 'add_lesson':
        topic = request.POST.get('topic', '').strip()
        notes = request.POST.get('notes', '').strip()
        homework = request.POST.get('homework', '').strip()
        date_str = request.POST.get('date')
        file = request.FILES.get('file')
        if file:
            from main.validators import check_file_upload, validate_document_file
            is_valid, err_msg = check_file_upload(file, validate_document_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('group_detail', group_id=group.id)

        if topic:
            lesson = GroupLesson(
                group=group,
                topic=topic,
                notes=notes,
                homework=homework,
                file=file
            )
            if date_str:
                lesson.date = date_str
            lesson.save()
            messages.success(request, "Yangi dars mavzusi va konspekti muvaffaqiyatli saqlandi!")
        else:
            messages.error(request, "Dars mavzusini kiritish majburiy!")
        return redirect('group_detail', group_id=group.id)

    students = list(group.students.all())
    student_ids = [s.id for s in students]
    lessons = GroupLesson.objects.filter(group=group).order_by('-date', '-created_at')

    # Reyting (Leaderboard) hisoblash - Bulk Aggregation
    leaderboard = []
    quizzes = list(Quiz.objects.filter(group=group))
    assignments = list(Assignment.objects.filter(group=group))
    
    # Get group memberships to know when each student joined
    memberships = GroupStudentMembership.objects.filter(group=group).values('student_id', 'joined_at')
    membership_joined_map = {m['student_id']: m['joined_at'] for m in memberships}

    quiz_scores = StudentQuizResult.objects.filter(student_id__in=student_ids, quiz__in=quizzes).values('student_id').annotate(total_score=Sum('score'))
    quiz_score_map = {item['student_id']: item['total_score'] for item in quiz_scores}

    hw_scores = AssignmentSubmission.objects.filter(student_id__in=student_ids, assignment__in=assignments, grade__isnull=False).values('student_id').annotate(total_grade=Sum('grade'))
    hw_score_map = {item['student_id']: item['total_grade'] for item in hw_scores}

    att_counts = Attendance.objects.filter(student_id__in=student_ids, group=group).values('student_id', 'status').annotate(cnt=Count('id'))
    att_total_map = {}
    att_present_map = {}
    for item in att_counts:
        sid = item['student_id']
        st = item['status']
        cnt = item['cnt']
        att_total_map[sid] = att_total_map.get(sid, 0) + cnt
        if st == 'present':
            att_present_map[sid] = cnt

    for student in students:
        joined_at = membership_joined_map.get(student.id)
        
        # Calculate max possible quiz and assignment scores dynamically based on joined_at
        student_total_quiz_max = sum(q.max_score for q in quizzes if not joined_at or joined_at <= q.created_at)
        student_total_hw_max = sum(a.max_score for a in assignments if not joined_at or joined_at <= a.created_at)

        total_quiz_score = quiz_score_map.get(student.id, 0)
        avg_quiz_percent = (total_quiz_score / student_total_quiz_max * 100) if student_total_quiz_max > 0 else None

        total_hw_score = hw_score_map.get(student.id, 0)
        avg_hw_percent = (total_hw_score / student_total_hw_max * 100) if student_total_hw_max > 0 else None

        total_att = att_total_map.get(student.id, 0)
        present_att = att_present_map.get(student.id, 0)
        attendance_rate = (present_att / total_att * 100) if total_att > 0 else 100

        components = []
        weights = []
        if avg_quiz_percent is not None:
            components.append(avg_quiz_percent)
            weights.append(0.4)
        if avg_hw_percent is not None:
            components.append(avg_hw_percent)
            weights.append(0.4)

        components.append(attendance_rate)
        weights.append(0.2)

        total_weight = sum(weights)
        overall_score = (sum(c * w for c, w in zip(components, weights)) / total_weight) if total_weight > 0 else 0

        leaderboard.append({
            'student': student,
            'avg_quiz': avg_quiz_percent,
            'avg_hw': avg_hw_percent,
            'attendance': attendance_rate,
            'overall_score': round(overall_score, 1)
        })

    # Sort leaderboard by overall_score descending
    leaderboard = sorted(leaderboard, key=lambda x: x['overall_score'], reverse=True)

    return render(request, 'group_detail.html', {
        'group': group,
        'students': students,
        'teacher': teacher,
        'lessons': lessons,
        'leaderboard': leaderboard,
    })


DAYS_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
DAY_NAMES = {
    'monday': 'Dushanba',
    'tuesday': 'Seshanba',
    'wednesday': 'Chorshanba',
    'thursday': 'Payshanba',
    'friday': 'Juma',
    'saturday': 'Shanba',
}

@teacher_required
def teacher_schedule_view(request):
    teacher = request.user

    groups = list(teacher.teachers_groups.all())
    group_ids = [g.id for g in groups]

    schedules = Schedule.objects.filter(group_id__in=group_ids, teacher=teacher).order_by('start_time')
    schedule_map = {}
    for sch in schedules:
        key = (sch.group_id, sch.day)
        if key not in schedule_map:
            schedule_map[key] = []
        schedule_map[key].append(f"{sch.start_time.strftime('%H:%M')} - {sch.end_time.strftime('%H:%M')}")

    jadval_data = []
    for group in groups:
        group_row = {
            'id': group.id,
            'name': group.name,
            'schedule_list': []
        }

        for day in DAYS_ORDER:
            vaqtlar = schedule_map.get((group.id, day), [])

            group_row['schedule_list'].append({
                'day': day,
                'day_name': DAY_NAMES[day],
                'vaqtlar': vaqtlar
            })

        jadval_data.append(group_row)

    context = {
        'groups': groups,
        'jadval_data': jadval_data,
        'teacher': teacher,
    }
    return render(request, 'teacher_dars_table.html', context)

@teacher_required
def create_quiz(request):
    teacher = request.user

    groups = teacher.teachers_groups.all()

    quizzes = Quiz.objects.filter(teacher=teacher) \
        .annotate(question_count=Count('questions')) \
        .select_related('group') \
        .order_by('-created_at')

    return render(request, 'create_quiz.html', {
        'groups': groups,
        'teacher': teacher,
        'quizzes': quizzes
    })

@teacher_required
@transaction.atomic
def add_questions(request, group_id):
    teacher = request.user

    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        time_limit = request.POST.get('time_limit')
        max_score = request.POST.get('max_score')
        total_questions = int(request.POST.get('total_questions', 0))

        if not title:
            return redirect('add_questions', group_id=group.id)

        # Avval barcha savollarni validatsiya qilamiz (DB ga yozmasdan)
        valid_questions_data = []
        for i in range(1, total_questions + 1):
            question_text = request.POST.get(f'question_{i}', '').strip()
            if not question_text:
                continue

            answers_data = []
            correct_answer = request.POST.get(f'question_{i}_correct', '')
            for j in range(1, 21):
                ans_key = f'question_{i}_answer_{j}'
                answer_text = request.POST.get(ans_key, '').strip()
                if answer_text:
                    answers_data.append((answer_text, str(j) == correct_answer))

            if len(answers_data) < 2:
                continue
            if not any(is_correct for _, is_correct in answers_data):
                continue

            valid_questions_data.append((question_text, answers_data))

        # Hech qanday to'g'ri savol yo'q bo'lsa — DB ga hech narsa yozmaymiz
        if not valid_questions_data:
            messages.error(request, "Hech bo'lmaganda bitta to'g'ri shakllantirilgan savol kiritilishi shart (kamida 2 ta javob va 1 ta to'g'ri javob bilan).", extra_tags='test_modal')
            return redirect('add_questions', group_id=group.id)

        # Transaksiya ichida Quiz + Question + Answer yaratamiz (bulk)
        quiz = Quiz.objects.create(
            title=title,
            group=group,
            teacher=teacher,
            time_limit=time_limit,
            max_score=max_score
        )

        questions_to_create = [Question(quiz=quiz, text=q_text) for q_text, _ in valid_questions_data]
        created_questions = Question.objects.bulk_create(questions_to_create)

        answers_to_create = []
        for question, (_, answers_data) in zip(created_questions, valid_questions_data):
            for text, is_correct in answers_data:
                answers_to_create.append(Answer(question=question, text=text, is_correct=is_correct))
        Answer.objects.bulk_create(answers_to_create)

        log_action(teacher, "Test Yaratildi", f"Yangi test yaratildi: '{title}' (Guruh: {group.name}, Savollar soni: {len(valid_questions_data)}, ID: {quiz.id})", request)
        messages.success(request, "Test muvaffaqiyatli qo'shildi!", extra_tags='test_modal')
        return redirect('create_quiz')

    return render(request, 'teacher-test-group.html', {
        'group': group,
        'teacher': teacher,
    })

@teacher_required
def quiz_detail(request, quiz_id):
    teacher = request.user

    quiz = get_object_or_404(Quiz, id=quiz_id, teacher=teacher)
    questions = quiz.questions.prefetch_related('answers')

    if request.method == 'POST':
        # Quiz nomi va vaqtini yangilash
        quiz.title = request.POST.get('title', quiz.title)
        quiz.time_limit = int(request.POST.get('time_limit', quiz.time_limit))
        quiz.max_score = int(request.POST.get('max_score', quiz.max_score))
        quiz.save()

        # N+1 UPDATE muammosini hal qilamiz: bulk_update ishlatamiz
        with transaction.atomic():
            questions_to_update = []
            answers_to_update = []

            for question in questions:
                q_text = request.POST.get(f'question_{question.id}')
                if q_text and q_text != question.text:
                    question.text = q_text
                    questions_to_update.append(question)

                correct_answer_id = request.POST.get(f'correct_{question.id}')
                for answer in question.answers.all():
                    a_text = request.POST.get(f'answer_{answer.id}')
                    changed = False
                    if a_text and a_text != answer.text:
                        answer.text = a_text
                        changed = True
                    new_correct = str(answer.id) == correct_answer_id
                    if answer.is_correct != new_correct:
                        answer.is_correct = new_correct
                        changed = True
                    if changed:
                        answers_to_update.append(answer)

            if questions_to_update:
                Question.objects.bulk_update(questions_to_update, ['text'])
            if answers_to_update:
                Answer.objects.bulk_update(answers_to_update, ['text', 'is_correct'])

        messages.success(request, "Test muvaffaqiyatli yangilandi.", extra_tags='test_modal')
        return redirect('create_quiz')

    return render(request, 'quiz_detail.html', {
        'quiz': quiz,
        'questions': questions,
        'teacher': teacher,
    })

@teacher_required
def teacher_view_results(request, quiz_id):
    teacher = request.user

    quiz = get_object_or_404(Quiz, id=quiz_id, teacher=teacher)
    group = quiz.group

    # Guruhdagi barcha o‘quvchilar bilan birga joined_at ni ham olish
    memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
    results = StudentQuizResult.objects.filter(quiz=quiz).select_related('student')
    result_map = {result.student.id: result for result in results}

    students_data = []
    total_questions = quiz.questions.count()

    for membership in memberships:
        student = membership.student

        # Agar o‘quvchi quiz yuklangandan keyin qo‘shilgan bo‘lsa, o‘tkazib yuboramiz
        if membership.joined_at > quiz.created_at:
            continue

        result = result_map.get(student.id)
        if result:
            correct_count = round((result.score / quiz.max_score) * total_questions)
        else:
            correct_count = None  # hali bajarmagan

        students_data.append({
            'student': student,
            'result': result,
            'correct_count': correct_count,
            'total_questions': total_questions
        })

    return render(request, 'teacher_quiz_results.html', {
        'teacher': teacher,
        'quiz': quiz,
        'students_data': students_data,
    })



@teacher_required
def teacher_deadline(request):
    teacher = request.user

    groups = teacher.teachers_groups.all()
    assignments = Assignment.objects.filter(teacher=teacher).select_related('group').order_by('-created_at')

    if request.method == 'POST':
        title = request.POST.get('title')
        group_id = request.POST.get('group_id')
        deadline_str = request.POST.get('deadline')
        file = request.FILES.get('file')
        max_score = request.POST.get('max_score')

        # Barcha maydonlar to‘ldirilganini tekshirish
        if title and group_id and deadline_str and file and max_score:
            from main.validators import validate_document_file
            from django.core.exceptions import ValidationError
            try:
                validate_document_file(file)
            except ValidationError as ve:
                return render(request, 'teacher-upload-deadline.html', {
                    'teacher': teacher,
                    'groups': groups,
                    'assignments': assignments,
                    'error': ve.message
                })
            try:
                deadline = timezone.datetime.fromisoformat(deadline_str)
                deadline = timezone.make_aware(deadline)  # timezone bilan
            except Exception:
                return render(request, 'teacher-upload-deadline.html', {
                    'teacher': teacher,
                    'groups': groups,
                    'assignments': assignments,
                    'error': "Noto‘g‘ri sana kiritildi."
                })

            # Muddat kamida 3 kun oldinga bo‘lishi kerak
            if deadline < timezone.now() + timedelta(days=3):
                return render(request, 'teacher-upload-deadline.html', {
                    'teacher': teacher,
                    'groups': groups,
                    'assignments': assignments,
                    'error': "Topshiriq muddati kamida 3 kun keyingi sana bo‘lishi kerak."
                })

            group = get_object_or_404(Group, id=group_id, teachers=teacher)
            assignment = Assignment.objects.create(
                title=title,
                teacher=teacher,
                group=group,
                deadline=deadline,
                file=file,
                max_score=max_score
            )
            log_action(teacher, "Topshiriq Yaratildi", f"'{group.name}' guruhi uchun yangi topshiriq yaratildi: '{title}' (Maks ball: {max_score}, ID: {assignment.id})", request)
            messages.success(request, "Topshiriq muvaffaqiyatli qo‘shildi!", extra_tags='topshir_modal')
            return redirect('teacher_deadline')

    return render(request, 'teacher-upload-deadline.html', {
        'teacher': teacher,
        'groups': groups,
        'assignments': assignments
    })


@teacher_required
def edit_assignment(request, assignment_id):
    teacher = request.user
    if request.method != 'POST':
        return HttpResponseBadRequest("Faqat POST so‘rov qabul qilinadi.")

    assignment = get_object_or_404(Assignment, id=assignment_id, teacher=teacher)

    # POST'dan kelgan ma'lumotlar
    new_title = request.POST.get('title')
    new_deadline = request.POST.get('deadline')
    new_max_score = request.POST.get('max_score')
    new_group_id = request.POST.get('group_id')
    new_file = request.FILES.get('file')

    # Faqat o‘zgartirilganlarini yangilaymiz
    if new_title and new_title != assignment.title:
        assignment.title = new_title

    if new_max_score and str(assignment.max_score) != str(new_max_score):
        assignment.max_score = new_max_score

    if new_deadline and assignment.deadline.strftime('%Y-%m-%dT%H:%M') != new_deadline:
        try:
            parsed_deadline = timezone.datetime.fromisoformat(new_deadline)
            aware_deadline = timezone.make_aware(parsed_deadline)
            if aware_deadline < timezone.now() + timedelta(days=3):
                messages.error(request, "Topshiriq muddati kamida 3 kun keyingi sana bo‘lishi kerak.", extra_tags='topshir_modal')
                return redirect('teacher_deadline')
            assignment.deadline = aware_deadline
        except Exception:
            messages.error(request, "Sana formati noto'g'ri.", extra_tags='topshir_modal')
            return redirect('teacher_deadline')

    if new_group_id and str(assignment.group.id) != str(new_group_id):
        try:
            new_group = Group.objects.get(id=new_group_id, teachers=teacher)
            assignment.group = new_group
        except Group.DoesNotExist:
            return HttpResponseBadRequest("Guruh topilmadi.")

    if new_file:
        from main.validators import validate_document_file
        from django.core.exceptions import ValidationError
        try:
            validate_document_file(new_file)
        except ValidationError as ve:
            messages.error(request, ve.message, extra_tags='topshir_modal')
            return redirect('teacher_deadline')
        assignment.file = new_file

    # Saqlash
    assignment.save()
    log_action(teacher, "Topshiriq Tahrirlandi", f"Topshiriq tahrirlandi: '{assignment.title}' (Guruh: {assignment.group.name}, ID: {assignment.id})", request)
    messages.success(request, "Topshiriq muvaffaqiyatli yangilandi!", extra_tags='topshir_modal')
    return redirect('teacher_deadline')

@teacher_required
def teacher_attendance_groups(request):
    teacher = request.user

    # Faqat o'ziga tegishli guruhlarni oladi
    groups = teacher.teachers_groups.all()

    return render(request, 'teacher_attendance_groups.html', {
        'teacher': teacher,
        'groups': groups
    })


@teacher_required
def submit_attendance(request, group_id):
    teacher = request.user
    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    # Umumiy eligibility tekshiruvi (check_attendance_eligibility yordamida)
    allowed, error_msg = check_attendance_eligibility(teacher, group)
    if not allowed:
        messages.error(request, error_msg)
        return redirect('teacher_attendance_groups')

    today = timezone.localdate()
    days_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday',
                3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
    today_day = days_map[timezone.localtime().weekday()]
    schedule = Schedule.objects.filter(group=group, day=today_day).first()

    # POST bilan kelgan davomat ma'lumotlarini saqlaymiz
    if request.method == 'POST':
        students = list(group.students.all())
        # bulk_create: N ta INSERT o'rniga 1 ta INSERT
        attendance_list = [
            Attendance(
                student=s,
                teacher=teacher,
                group=group,
                date=today,
                status=request.POST.get(f'status_{s.id}', 'absent')
            )
            for s in students
        ]
        Attendance.objects.bulk_create(attendance_list)
        log_action(teacher, "Davomat Kiritildi", f"'{group.name}' guruhi uchun bugungi ({today.strftime('%d.%m.%Y')}) davomat kiritildi. (Ishtirokchilar soni: {len(attendance_list)})", request)
        messages.success(request, "Davomat muvaffaqiyatli saqlandi!")
        return redirect('teacher_attendance_groups')

    return render(request, 'teacher_submit_attendance.html', {
        'group': group,
        'students': group.students.all(),
        'schedule': schedule,
        'teacher': teacher,
    })

@teacher_required
def teacher_group_attendance(request, group_id):
    teacher = request.user

    # Faqat o‘ziga biriktirilgan guruh bo‘lishi shart
    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    students = group.students.all()
    range_val = request.GET.get('range', '7')

    # Barcha unikal sanalarni olamiz
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

    # Faqat tanlangan sanalardagi davomatlarni bitta so'rovda olamiz
    attendances = Attendance.objects.filter(group=group, date__in=filtered_dates)

    # Tezkor xotirada xaritalash: (student_id, date) -> status
    att_map = {(a.student_id, a.date): a.status for a in attendances}

    attendance_list = []
    for student in students:
        student_dates = []
        for d in filtered_dates:
            status = att_map.get((student.id, d))
            student_dates.append({
                'date': d,
                'status': status
            })
        attendance_list.append({
            'student': student,
            'dates': student_dates
        })

    return render(request, 'teacher_attendance_table.html', {
        'group': group,
        'dates': filtered_dates,
        'attendance_list': attendance_list,
        'teacher': teacher,
        'range_val': range_val,
        'total_dates_count': total_dates_count,
    })


@teacher_required
def teacher_assignment_submissions(request, assignment_id):
    teacher = request.user

    assignment = get_object_or_404(Assignment, id=assignment_id, teacher=teacher)
    group = assignment.group

    # Ushbu topshiriq sanasidan oldin guruhga qo‘shilgan o‘quvchilarni olamiz
    memberships = GroupStudentMembership.objects.filter(
        group=group,
        joined_at__lte=assignment.created_at  # yoki created_date bo'lsa
    ).select_related('student')

    # Barcha mavjud topshirilgan topshiriqlar
    submissions = AssignmentSubmission.objects.filter(assignment=assignment)
    submissions_dict = {s.student_id: s for s in submissions}  # tez izlash uchun

    student_data = []
    for membership in memberships:
        student = membership.student
        submission = submissions_dict.get(student.id)
        student_data.append({
            'student': student,
            'submission': submission  # None bo‘lishi ham mumkin
        })

    return render(request, 'teacher_assignment_submissions.html', {
        'assignment': assignment,
        'student_data': student_data,
        'teacher': teacher,
    })

@teacher_required
def grade_assignment(request):
    user = request.user

    if request.method == "POST":
        assignment_id = request.POST.get('assignment_id')
        student_id = request.POST.get('student_id')
        score_input = request.POST.get('score')

        try:
            score = int(score_input)
        except (ValueError, TypeError):
            messages.error(request, "Ball butun son bo‘lishi kerak.")
            return redirect('teacher_assignment_submissions', assignment_id=assignment_id)

        assignment = get_object_or_404(Assignment, id=assignment_id, teacher=user)
        submission = get_object_or_404(AssignmentSubmission, assignment=assignment, student_id=student_id)

        feedback_input = request.POST.get('feedback', '').strip()

        if score < 0:
            messages.error(request, "Ball manfiy bo‘lishi mumkin emas.")
        elif score > assignment.max_score:
            messages.error(request, f"Ball maksimal {assignment.max_score} dan oshmasligi kerak.")
        else:
            submission.grade = score
            submission.feedback = feedback_input
            submission.save()
            log_action(user, "Topshiriq Baholandi", f"{submission.student.get_full_name()}ning '{assignment.title}' topshirig'i baholandi. Ball: {score}/{assignment.max_score}", request)
            messages.success(request, "Baholash saqlandi.")

        return redirect('teacher_assignment_submissions', assignment_id=assignment_id)

    else:
        return HttpResponseBadRequest("Faqat POST so‘rovlari qabul qilinadi.")


@teacher_required
def quick_grade_view(request):
    teacher = request.user

    if request.method == 'POST':
        submission_id = request.POST.get('submission_id')
        score_input = request.POST.get('score')

        try:
            score = int(score_input)
        except (ValueError, TypeError):
            messages.error(request, "Ball butun son bo'lishi kerak.")
            return redirect('quick_grade')

        submission = get_object_or_404(
            AssignmentSubmission, 
            id=submission_id, 
            assignment__group__teachers=teacher,
            student__student_groups__teachers=teacher
        )
        assignment = submission.assignment

        feedback_input = request.POST.get('feedback', '').strip()

        if score < 0:
            messages.error(request, "Ball manfiy bo'lishi mumkin emas.")
        elif score > assignment.max_score:
            messages.error(request, f"Ball maksimal {assignment.max_score} dan oshmasligi kerak.")
        else:
            submission.grade = score
            submission.feedback = feedback_input
            submission.save()
            log_action(teacher, "Topshiriq Baholandi (Tezkor)", f"{submission.student.get_full_name()}ning '{assignment.title}' topshirig'i baholandi. Ball: {score}/{assignment.max_score}", request)
            messages.success(request, f"{submission.student.get_full_name()}ning topshirig'i baholandi.")

        return redirect('quick_grade')

    # Baholanmagan topshiriqlarni olamiz
    pending_submissions = AssignmentSubmission.objects.filter(
        assignment__group__teachers=teacher,
        student__student_groups__teachers=teacher,
        grade__isnull=True
    ).distinct().select_related('student', 'assignment', 'assignment__group').order_by('-submitted_at')

    return render(request, 'teacher_quick_grade.html', {
        'submissions': pending_submissions,
        'teacher': teacher
    })


@teacher_required
def teacher_check_class_ajax(request, group_id):
    teacher = request.user

    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    # DRY: check_attendance_eligibility yordamida tekshirish
    allowed, error_msg = check_attendance_eligibility(teacher, group)
    if not allowed:
        return JsonResponse({'allowed': False, 'error': error_msg})

    return JsonResponse({'allowed': True})


@teacher_required
def teacher_media_gallery(request):
    teacher = request.user

    groups = teacher.teachers_groups.all()
    videos = GroupVideo.objects.filter(group__in=groups).select_related('group', 'teacher').order_by('-created_at')

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        group_id = request.POST.get('group_id')
        video_file = request.FILES.get('video_file')
        youtube_link = request.POST.get('youtube_link')

        if not title or not group_id:
            messages.error(request, "Sarlavha va Guruh tanlanishi majburiy!")
            return redirect('teacher_media_gallery')

        if not video_file and not youtube_link:
            messages.error(request, "Iltimos, video fayl yuklang yoki YouTube havola kiriting!")
            return redirect('teacher_media_gallery')

        if video_file:
            from main.validators import check_file_upload, validate_video_file
            is_valid, err_msg = check_file_upload(video_file, validate_video_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('teacher_media_gallery')

        group = get_object_or_404(Group, id=group_id, teachers=teacher)

        video = GroupVideo.objects.create(
            title=title,
            description=description,
            group=group,
            teacher=teacher,
            video_file=video_file,
            youtube_link=youtube_link
        )
        log_action(teacher, "Video Yuklandi", f"Yangi video dars yuklandi: '{title}' (Guruh: {group.name}, ID: {video.id})", request)
        messages.success(request, "Video dars muvaffaqiyatli yuklandi!", extra_tags='video_toast')
        return redirect('teacher_media_gallery')

    return render(request, 'teacher_media_gallery.html', {
        'teacher': teacher,
        'groups': groups,
        'videos': videos
    })


@teacher_required
def teacher_edit_video(request, video_id):
    teacher = request.user

    video = get_object_or_404(GroupVideo, id=video_id, teacher=teacher)

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        group_id = request.POST.get('group_id')
        video_file = request.FILES.get('video_file')
        youtube_link = request.POST.get('youtube_link')

        if video_file:
            from main.validators import check_file_upload, validate_video_file
            is_valid, err_msg = check_file_upload(video_file, validate_video_file)
            if not is_valid:
                messages.error(request, err_msg)
                return redirect('teacher_media_gallery')

        if title:
            video.title = title
        video.description = description
        if youtube_link is not None:
            video.youtube_link = youtube_link
        if group_id:
            group = get_object_or_404(Group, id=group_id, teachers=teacher)
            video.group = group
        if video_file:
            video.video_file = video_file

        video.save()
        log_action(teacher, "Video Tahrirlandi", f"Video dars ma'lumotlari tahrirlandi: '{video.title}' (Guruh: {video.group.name}, ID: {video.id})", request)
        messages.success(request, "Video dars muvaffaqiyatli yangilandi!", extra_tags='video_toast')
    return redirect('teacher_media_gallery')


@teacher_required
def teacher_delete_video(request, video_id):
    teacher = request.user

    video = get_object_or_404(GroupVideo, id=video_id, teacher=teacher)
    video_title = video.title
    group_name = video.group.name
    video.delete()
    log_action(teacher, "Video O'chirildi", f"Video dars o'chirildi: '{video_title}' (Guruh: {group_name})", request)
    messages.success(request, "Video dars muvaffaqiyatli o'chirildi!", extra_tags='video_toast')
    return redirect('teacher_media_gallery')


@teacher_required
def teacher_past_questions_api(request):
    teacher = request.user

    quizzes = Quiz.objects.filter(teacher=teacher)
    # select_related('quiz') qo'shildi: loop ichida N+1 oldini olish uchun
    questions = Question.objects.filter(quiz__in=quizzes).prefetch_related('answers').select_related('quiz')

    data = []
    for q in questions:
        answers = []
        correct_index = 1
        for idx, ans in enumerate(q.answers.all(), 1):
            answers.append(ans.text)
            if ans.is_correct:
                correct_index = idx
        data.append({
            'id': q.id,
            'quiz_title': q.quiz.title,
            'text': q.text,
            'answers': answers,
            'correct_index': correct_index
        })

    return JsonResponse({'questions': data})


@teacher_required
def teacher_subjects_view(request):
    teacher = request.user

    subjects = teacher.subjects.prefetch_related(
        Prefetch('materials', queryset=SubjectMaterial.objects.order_by('-created_at')),
        Prefetch('books', queryset=Book.objects.order_by('-created_at'))
    ).order_by('name')

    if request.method == 'POST':
        if request.POST.get('action') == 'upload_material':
            subject_id = request.POST.get('subject')
            subject = get_object_or_404(Subject, id=subject_id)
            
            # Security check
            if subject not in subjects:
                messages.error(request, "Sizga ushbu fanga material yuklashga ruxsat berilmagan.")
                return redirect('teacher_subjects')

            material_file = request.FILES.get('material_file')
            if material_file:
                title = request.POST.get('material_title', '').strip()
                if not title:
                    title = material_file.name
                description = request.POST.get('material_description', '').strip()
                
                material = SubjectMaterial.objects.create(
                    subject=subject,
                    title=title,
                    description=description,
                    file=material_file,
                    uploaded_by=teacher
                )
                log_action(teacher, "Fan Materiali Yuklandi", f"Yangi fan materiali yuklandi: '{title}' (Fan: {subject.name}, ID: {material.id})", request)
                messages.success(request, f"{subject.name} faniga yangi material muvaffaqiyatli yuklandi.")
            else:
                messages.error(request, "Fayl tanlanmagan.")
            return redirect('teacher_subjects')

        elif request.POST.get('action') == 'upload_book':
            subject_id = request.POST.get('subject')
            subject = get_object_or_404(Subject, id=subject_id)
            
            # Security check
            if subject not in subjects:
                messages.error(request, "Sizga ushbu fanga kitob yuklashga ruxsat berilmagan.")
                return redirect('teacher_subjects')

            book_file = request.FILES.get('book_file')
            if book_file:
                if not book_file.name.lower().endswith('.pdf'):
                    messages.error(request, "Kitob faqat PDF formatida bo'lishi kerak.")
                    return redirect('teacher_subjects')

                title = request.POST.get('book_title', '').strip()
                if not title:
                    title = book_file.name
                description = request.POST.get('book_description', '').strip()
                
                book = Book.objects.create(
                    subject=subject,
                    title=title,
                    description=description,
                    file=book_file,
                    uploaded_by=teacher
                )
                log_action(teacher, "Fan Kitobi Yuklandi", f"Yangi fan kitobi yuklandi: '{title}' (Fan: {subject.name}, ID: {book.id})", request)
                messages.success(request, f"{subject.name} faniga yangi kitob muvaffaqiyatli yuklandi.")
            else:
                messages.error(request, "Fayl tanlanmagan.")
            return redirect('teacher_subjects')

    subjects_data = [
        {'subject': subject, 'materials': subject.materials.all(), 'books': subject.books.all()}
        for subject in subjects
    ]

    return render(request, 'teacher-fanlar.html', {
        'teacher': teacher,
        'subjects_data': subjects_data
    })


@teacher_required
def delete_book_teacher(request, book_id):
    teacher = request.user
    book = get_object_or_404(Book, id=book_id)
    subject = book.subject
    
    # Check permission
    if subject not in teacher.subjects.all():
        messages.error(request, "Sizga ushbu fandan kitob o'chirishga ruxsat berilmagan.")
        return redirect('teacher_subjects')
        
    book_title = book.title
    if book.file:
        if os.path.exists(book.file.path):
            os.remove(book.file.path)
            
    book.delete()
    log_action(teacher, "Kitob O'chirildi (O'qituvchi)", f"Kitob o'chirildi: {book_title} (Fan: {subject.name})", request)
    messages.success(request, "Kitob muvaffaqiyatli o'chirildi.")
    return redirect('teacher_subjects')


@teacher_required
def delete_subject_material_teacher(request, material_id):
    teacher = request.user

    material = get_object_or_404(SubjectMaterial, id=material_id)
    subject = material.subject

    # Security check: faqat o'zi yuklagan materialni o'chira oladi
    if material.uploaded_by != teacher:
        messages.error(request, "Siz faqat o'zingiz yuklagan materiallarni o'chira olasiz.")
        return redirect('teacher_subjects')

    material_title = material.title
    material.delete()
    log_action(teacher, "Fan Materiali O'chirildi", f"Fan materiali o'chirildi: '{material_title}' (Fan: {subject.name})", request)
    messages.success(request, f"'{material_title}' materiali muvaffaqiyatli o'chirildi.")
    return redirect('teacher_subjects')


@teacher_required
def export_attendance_excel(request, group_id):
    import tablib
    teacher = request.user
    group = get_object_or_404(Group, id=group_id, teachers=teacher)
    students = group.students.all()
    attendances = Attendance.objects.filter(group=group).order_by('date')
    dates = sorted(set(attendances.values_list('date', flat=True)))

    headers = ['F.I.SH.'] + [d.strftime('%d.%m.%Y') for d in dates]

    att_by_student = {}
    for att in attendances:
        att_by_student.setdefault(att.student_id, {})[att.date] = att.get_status_display()

    data = tablib.Dataset(headers=headers)
    for s in students:
        row = [s.get_full_name()]
        for date in dates:
            row.append(att_by_student.get(s.id, {}).get(date, '-'))
        data.append(row)

    response = HttpResponse(data.xlsx, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{group.name}_davomat.xlsx"'
    return response


@teacher_required
def export_grades_excel(request, group_id):
    import tablib
    teacher = request.user
    group = get_object_or_404(Group, id=group_id, teachers=teacher)
    students = group.students.all()
    quizzes = list(Quiz.objects.filter(group=group))
    assignments = list(Assignment.objects.filter(group=group))

    headers = ['F.I.SH.', 'Davomat rate (%)', 'Quiz ball (%)', 'Topshiriq ball (%)', 'Umumiy ball (%)']

    student_ids = [s.id for s in students]

    memberships = GroupStudentMembership.objects.filter(group=group).values('student_id', 'joined_at')
    membership_joined_map = {m['student_id']: m['joined_at'] for m in memberships}

    quiz_scores = StudentQuizResult.objects.filter(student_id__in=student_ids, quiz__in=quizzes).values('student_id').annotate(total_score=Sum('score'))
    quiz_score_map = {item['student_id']: item['total_score'] for item in quiz_scores}

    hw_scores = AssignmentSubmission.objects.filter(student_id__in=student_ids, assignment__in=assignments, grade__isnull=False).values('student_id').annotate(total_grade=Sum('grade'))
    hw_score_map = {item['student_id']: item['total_grade'] for item in hw_scores}

    att_counts = Attendance.objects.filter(student_id__in=student_ids, group=group).values('student_id', 'status').annotate(cnt=Count('id'))
    att_total_map = {}
    att_present_map = {}
    for item in att_counts:
        sid = item['student_id']
        st = item['status']
        cnt = item['cnt']
        att_total_map[sid] = att_total_map.get(sid, 0) + cnt
        if st == 'present':
            att_present_map[sid] = cnt

    data = tablib.Dataset(headers=headers)
    for student in students:
        joined_at = membership_joined_map.get(student.id)
        student_total_quiz_max = sum(q.max_score for q in quizzes if not joined_at or joined_at <= q.created_at)
        student_total_hw_max = sum(a.max_score for a in assignments if not joined_at or joined_at <= a.created_at)

        total_quiz_score = quiz_score_map.get(student.id, 0)
        avg_quiz_percent = (total_quiz_score / student_total_quiz_max * 100) if student_total_quiz_max > 0 else 0

        total_hw_score = hw_score_map.get(student.id, 0)
        avg_hw_percent = (total_hw_score / student_total_hw_max * 100) if student_total_hw_max > 0 else 0

        total_att = att_total_map.get(student.id, 0)
        present_att = att_present_map.get(student.id, 0)
        attendance_rate = (present_att / total_att * 100) if total_att > 0 else 100

        components = [avg_quiz_percent, avg_hw_percent, attendance_rate]
        weights = [0.4, 0.4, 0.2]
        overall_score = sum(c * w for c, w in zip(components, weights))

        data.append([
            student.get_full_name(),
            round(attendance_rate, 1),
            round(avg_quiz_percent, 1),
            round(avg_hw_percent, 1),
            round(overall_score, 1)
        ])

    response = HttpResponse(data.xlsx, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{group.name}_reyting.xlsx"'
    return response


@teacher_required
def export_grades_pdf(request, group_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    teacher = request.user
    group = get_object_or_404(Group, id=group_id, teachers=teacher)
    students = group.students.all()
    quizzes = list(Quiz.objects.filter(group=group))
    assignments = list(Assignment.objects.filter(group=group))

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{group.name}_reyting.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontName=FONT_BOLD,
        fontSize=18,
        spaceAfter=20,
        textColor=colors.HexColor('#002B49')
    )

    story.append(Paragraph(f"{group.name} Guruh Reytingi", title_style))
    story.append(Spacer(1, 10))

    table_data = [['#', 'F.I.SH.', 'Davomat (%)', 'Quiz (%)', 'Topshiriq (%)', 'Umumiy Ball']]

    student_ids = [s.id for s in students]
    memberships = GroupStudentMembership.objects.filter(group=group).values('student_id', 'joined_at')
    membership_joined_map = {m['student_id']: m['joined_at'] for m in memberships}

    quiz_scores = StudentQuizResult.objects.filter(student_id__in=student_ids, quiz__in=quizzes).values('student_id').annotate(total_score=Sum('score'))
    quiz_score_map = {item['student_id']: item['total_score'] for item in quiz_scores}

    hw_scores = AssignmentSubmission.objects.filter(student_id__in=student_ids, assignment__in=assignments, grade__isnull=False).values('student_id').annotate(total_grade=Sum('grade'))
    hw_score_map = {item['student_id']: item['total_grade'] for item in hw_scores}

    att_counts = Attendance.objects.filter(student_id__in=student_ids, group=group).values('student_id', 'status').annotate(cnt=Count('id'))
    att_total_map = {}
    att_present_map = {}
    for item in att_counts:
        sid = item['student_id']
        st = item['status']
        cnt = item['cnt']
        att_total_map[sid] = att_total_map.get(sid, 0) + cnt
        if st == 'present':
            att_present_map[sid] = cnt

    leaderboard_raw = []
    for student in students:
        joined_at = membership_joined_map.get(student.id)
        student_total_quiz_max = sum(q.max_score for q in quizzes if not joined_at or joined_at <= q.created_at)
        student_total_hw_max = sum(a.max_score for a in assignments if not joined_at or joined_at <= a.created_at)

        total_quiz_score = quiz_score_map.get(student.id, 0)
        avg_quiz_percent = (total_quiz_score / student_total_quiz_max * 100) if student_total_quiz_max > 0 else 0

        total_hw_score = hw_score_map.get(student.id, 0)
        avg_hw_percent = (total_hw_score / student_total_hw_max * 100) if student_total_hw_max > 0 else 0

        total_att = att_total_map.get(student.id, 0)
        present_att = att_present_map.get(student.id, 0)
        attendance_rate = (present_att / total_att * 100) if total_att > 0 else 100

        components = [avg_quiz_percent, avg_hw_percent, attendance_rate]
        weights = [0.4, 0.4, 0.2]
        overall_score = sum(c * w for c, w in zip(components, weights))
        leaderboard_raw.append((student.get_full_name(), attendance_rate, avg_quiz_percent, avg_hw_percent, overall_score))

    leaderboard_raw.sort(key=lambda x: x[4], reverse=True)

    for idx, item in enumerate(leaderboard_raw, 1):
        table_data.append([
            str(idx),
            item[0],
            f"{round(item[1], 1)}%",
            f"{round(item[2], 1)}%",
            f"{round(item[3], 1)}%",
            str(round(item[4], 1))
        ])

    t = Table(table_data, colWidths=[30, 200, 70, 70, 80, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#002B49')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (1,1), (1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F4F6F8')),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#E1E6EB')),
        ('FONTNAME', (0,0), (-1,-1), FONT_NAME),
        ('FONTNAME', (0,0), (-1,0), FONT_BOLD),
        ('FONTSIZE', (0,0), (-1,-1), 10),
    ]))
    story.append(t)
    doc.build(story)
    return response
