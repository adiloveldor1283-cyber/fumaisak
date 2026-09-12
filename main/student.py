from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import models, transaction
from django.db.models import Sum, Count
from DjangoProject.utils import rate_limit
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.cache import cache
from main.models import Quiz, Group, StudentQuizResult, Answer, StudentAnswer, Schedule, DAYS_OF_WEEK, Assignment, \
    AssignmentSubmission, CustomUser, GroupStudentMembership, StudentPayment, GroupPaymentInfo, Attendance, GroupLesson, GroupVideo, Subject, SubjectMaterial, AIQuiz, AIAnswer, StudentAIAnswer, DTMExam, DTMRegistration, Book, WalletTransaction
from django.contrib.auth import update_session_auth_hash
from collections import OrderedDict
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Q
from .utils import log_action



def get_all_student_scores(student_ids=None):
    # 1. Fetch memberships
    membership_qs = GroupStudentMembership.objects.select_related('student', 'group')
    if student_ids is not None:
        membership_qs = membership_qs.filter(student_id__in=student_ids)

    student_groups_info = {}
    all_student_ids = set()
    all_group_ids = set()
    student_obj_map = {}

    for m in membership_qs:
        sid = m.student_id
        gid = m.group_id
        if m.student.role != 'student':
            continue
        all_student_ids.add(sid)
        all_group_ids.add(gid)
        student_obj_map[sid] = m.student
        if sid not in student_groups_info:
            student_groups_info[sid] = {}
        student_groups_info[sid][gid] = m.joined_at

    if not all_student_ids:
        return {}

    # 2. Fetch all quizzes and assignments in these groups
    quizzes = Quiz.objects.filter(group_id__in=all_group_ids).only('id', 'group_id', 'created_at', 'max_score')
    assignments = Assignment.objects.filter(group_id__in=all_group_ids).only('id', 'group_id', 'created_at', 'max_score')

    # Organize quizzes and assignments by group
    quizzes_by_group = {}
    assignments_by_group = {}
    for q in quizzes:
        quizzes_by_group.setdefault(q.group_id, []).append(q)
    for a in assignments:
        assignments_by_group.setdefault(a.group_id, []).append(a)

    # 3. Fetch all quiz results and assignment submissions for these students
    quiz_results = StudentQuizResult.objects.filter(student_id__in=all_student_ids, quiz__in=quizzes).only('student_id', 'quiz_id', 'score')
    submissions = AssignmentSubmission.objects.filter(student_id__in=all_student_ids, assignment__in=assignments, grade__isnull=False).only('student_id', 'assignment_id', 'grade')

    quiz_results_dict = {(r.student_id, r.quiz_id): r.score for r in quiz_results}
    submissions_dict = {(s.student_id, s.assignment_id): s.grade for s in submissions}

    # 4. Calculate for each student in memory
    results = {}
    for sid in all_student_ids:
        group_joined_times = student_groups_info[sid]

        total_score = 0
        total_max_score = 0

        for gid, joined_at in group_joined_times.items():
            # Quizzes
            for quiz in quizzes_by_group.get(gid, []):
                if joined_at <= quiz.created_at:
                    score = quiz_results_dict.get((sid, quiz.id))
                    if score is not None:
                        total_score += score
                    total_max_score += quiz.max_score
            # Assignments
            for assignment in assignments_by_group.get(gid, []):
                if joined_at <= assignment.created_at:
                    grade = submissions_dict.get((sid, assignment.id))
                    if grade is not None:
                        total_score += grade
                    total_max_score += assignment.max_score

        percentage = round((total_score / total_max_score) * 100, 2) if total_max_score > 0 else 0
        results[sid] = {
            'student': student_obj_map[sid],
            'score_percent': percentage,
            'total_max': total_max_score
        }

    return results


def get_student_level_among_group(student):
    cache_key = f'student_level_info_{student.id}'
    cached_info = cache.get(cache_key)
    if cached_info:
        return cached_info

    memberships = GroupStudentMembership.objects.filter(student=student)
    group_ids = [m.group_id for m in memberships]

    # Barcha o‘quvchilar (shu guruhlarga tegishli)
    all_memberships = GroupStudentMembership.objects.filter(group_id__in=group_ids).select_related('student')
    student_ids = list(set(m.student_id for m in all_memberships if m.student.role == 'student'))

    scores = get_all_student_scores(student_ids)

    good = average = weak = 0
    student_percent = None
    total_count = 0

    for sid, data in scores.items():
        if data['total_max'] == 0:
            continue

        total_count += 1
        percent = data['score_percent']
        if sid == student.id:
            student_percent = percent

        if percent >= 90:
            good += 1
        elif percent >= 60:
            average += 1
        else:
            weak += 1

    if student_percent is None:
        level = "Noma’lum"
    elif student_percent >= 90:
        level = "Yaxshi"
    elif student_percent >= 60:
        level = "O‘rtacha"
    else:
        level = "Past"

    res = {
        'total': len(student_ids),
        'good': good,
        'average': average,
        'weak': weak,
        'student_level': level
    }
    cache.set(cache_key, res, 300) # Cache for 5 minutes
    return res


def get_top_students(current_student):
    cache_key = f'top_students_leaderboard_{current_student.id}'
    sorted_scores = cache.get(cache_key)

    if not sorted_scores:
        group_ids = list(GroupStudentMembership.objects.filter(student=current_student).values_list('group_id', flat=True))
        if not group_ids:
            return [], None
        
        classmate_ids = list(GroupStudentMembership.objects.filter(group_id__in=group_ids).values_list('student_id', flat=True).distinct())
        
        scores = get_all_student_scores(classmate_ids)
        student_scores = []
        for sid, data in scores.items():
            student_scores.append({
                'student': data['student'],
                'score_percent': data['score_percent']
            })

        sorted_scores = sorted(student_scores, key=lambda x: x['score_percent'], reverse=True)
        for idx, s in enumerate(sorted_scores, 1):
            s['rank'] = idx

        cache.set(cache_key, sorted_scores, 300) # Cache for 5 minutes

    top_10 = sorted_scores[:10]
    student_place = next((s for s in sorted_scores if s['student'].id == current_student.id), None)

    return top_10, student_place


def get_student_active_badge(student):
    memberships = GroupStudentMembership.objects.filter(student=student)
    group_ids = [m.group_id for m in memberships]
    if not group_ids:
        return None

    import datetime
    now_dt = datetime.datetime.now()
    if now_dt.month == 1:
        prev_month_num = 12
    else:
        prev_month_num = now_dt.month - 1

    attendances = list(Attendance.objects.filter(student=student, group_id__in=group_ids, date__month=prev_month_num))
    attendances_by_group = {}
    for att in attendances:
        attendances_by_group.setdefault(att.group_id, []).append(att)

    quizzes = list(Quiz.objects.filter(group_id__in=group_ids, created_at__month=prev_month_num))
    quizzes_by_group = {}
    for q in quizzes:
        quizzes_by_group.setdefault(q.group_id, []).append(q)

    assignments = list(Assignment.objects.filter(group_id__in=group_ids, created_at__month=prev_month_num))
    assignments_by_group = {}
    for a in assignments:
        assignments_by_group.setdefault(a.group_id, []).append(a)

    quiz_results = list(StudentQuizResult.objects.filter(student=student, quiz__in=quizzes))
    quiz_results_by_quiz = {r.quiz_id: r for r in quiz_results}

    submissions = list(AssignmentSubmission.objects.filter(student=student, assignment__in=assignments, grade__isnull=False))
    submissions_by_assignment = {s.assignment_id: s for s in submissions}

    best_badge = None
    for group_id in group_ids:
        group_atts = attendances_by_group.get(group_id, [])
        total_att = len(group_atts)
        present_att = sum(1 for att in group_atts if att.status == 'present')
        attendance_rate = (present_att / total_att) if total_att > 0 else 1.0

        group_quizzes = quizzes_by_group.get(group_id, [])
        group_assignments = assignments_by_group.get(group_id, [])

        scores = []
        for q in group_quizzes:
            res = quiz_results_by_quiz.get(q.id)
            if res:
                scores.append(res.score / q.max_score * 100 if q.max_score > 0 else 0)
            else:
                scores.append(0)
        for a in group_assignments:
            sub = submissions_by_assignment.get(a.id)
            if sub:
                scores.append(sub.grade / a.max_score * 100 if a.max_score > 0 else 0)
            else:
                scores.append(0)

        avg_score = sum(scores) / len(scores) if scores else 100.0

        badge = None
        if total_att > 0 or scores:
            if attendance_rate == 1.0 and avg_score >= 95.0:
                badge = {
                    'name': "Oltin Nishon",
                    'color': "#ffb000",
                    'icon': "fas fa-award",
                    'desc': f"O'tgan oyda davomat 100% va o'rtacha ball {round(avg_score)}% (100% chegirma!)"
                }
            elif attendance_rate >= 0.95 and avg_score >= 85.0:
                badge = {
                    'name': "Kumush Nishon",
                    'color': "#00f2fe",
                    'icon': "fas fa-medal",
                    'desc': f"O'tgan oyda davomat {round(attendance_rate * 100)}% va o'rtacha ball {round(avg_score)}% (50% chegirma!)"
                }
            elif attendance_rate >= 0.90 and avg_score >= 75.0:
                badge = {
                    'name': "Bronza Nishon",
                    'color': "#ff9f43",
                    'icon': "fas fa-trophy",
                    'desc': f"O'tgan oyda davomat {round(attendance_rate * 100)}% va o'rtacha ball {round(avg_score)}% (10% chegirma!)"
                }

        if badge:
            if not best_badge:
                best_badge = badge
            elif badge['name'] == "Oltin Nishon":
                best_badge = badge
            elif badge['name'] == "Kumush Nishon" and best_badge['name'] == "Bronza Nishon":
                best_badge = badge

    return best_badge


@login_required
def student_home_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_joined_times = {m.group.id: m.joined_at for m in memberships}
    group_ids = list(group_joined_times.keys())

    if not group_ids:
        total_assignments = 0
        completed_assignments = 0
        total_quizzes = 0
        completed_quizzes = 0
        assignments = Assignment.objects.none()
        quizzes = Quiz.objects.none()
    else:
        q_filter = Q()
        for group_id, joined_at in group_joined_times.items():
            q_filter |= Q(group_id=group_id, created_at__gte=joined_at)

        assignments = Assignment.objects.filter(q_filter)
        quizzes = Quiz.objects.filter(q_filter)

        total_assignments = assignments.count()
        completed_assignments = AssignmentSubmission.objects.filter(
            student=student,
            assignment__in=assignments
        ).values('assignment').distinct().count()

        total_quizzes = quizzes.count()
        completed_quizzes = StudentQuizResult.objects.filter(
            student=student,
            quiz__in=quizzes
        ).values('quiz').distinct().count()

    assignment_completion_percent = round((completed_assignments / total_assignments) * 100, 1) if total_assignments > 0 else 0
    assignment_missing_percent = round(100 - assignment_completion_percent, 1) if total_assignments > 0 else 0

    quiz_completion_percent = round((completed_quizzes / total_quizzes) * 100, 1) if total_quizzes > 0 else 0
    quiz_missing_percent = round(100 - quiz_completion_percent, 1) if total_quizzes > 0 else 0

    # Reyting va daraja
    top_students, student_place = get_top_students(student)
    level_info = get_student_level_among_group(student)

    # Davomat foizi (Joriy oy uchun)
    current_month = timezone.now().month
    att_current = Attendance.objects.filter(student=student, date__month=current_month)
    total_att_current = att_current.count()
    present_att_current = att_current.filter(status='present').count()
    current_attendance_percent = round((present_att_current / total_att_current) * 100, 1) if total_att_current > 0 else 100.0

    # Gamifikatsiya nishoni
    badge = get_student_active_badge(student)

    # Bugungi dars jadvali (Kun rejimi)
    import datetime
    today_num = datetime.datetime.today().weekday()
    day_mapping = {
        0: 'monday',
        1: 'tuesday',
        2: 'wednesday',
        3: 'thursday',
        4: 'friday',
        5: 'saturday',
        6: 'sunday'
    }
    today_day_key = day_mapping.get(today_num, 'monday')
    today_schedules = Schedule.objects.filter(
        group_id__in=group_ids,
        day=today_day_key
    ).select_related('group')

    # Telegram bot link generate
    telegram_link = None
    if not student.telegram_chat_id:
        from main.telegram_service import generate_telegram_link
        telegram_link = generate_telegram_link(student)

    context = {
        'student': student,
        'level_total': level_info['total'],
        'level_good': level_info['good'],
        'level_average': level_info['average'],
        'level_weak': level_info['weak'],
        'student_level': level_info['student_level'],
        'top_students': top_students,
        'student_place': student_place,
        'assignment_completion_percent': assignment_completion_percent,
        'assignment_missing_percent': assignment_missing_percent,
        'quiz_completion_percent': quiz_completion_percent,
        'quiz_missing_percent': quiz_missing_percent,
        'current_attendance_percent': current_attendance_percent,
        'badge': badge,
        'has_assignments': total_assignments > 0,
        'has_quizzes': total_quizzes > 0,
        'today_schedules': today_schedules,
        'telegram_link': telegram_link,
    }

    return render(request, 'student_home.html', context)


@login_required
def student_profile_view(request):
    student = request.user

    if student.role != 'student':
        return redirect('login')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'update_phone':
            from main.sms_service import clean_phone_number
            new_phone = request.POST.get('phone_number', '').strip()
            phone_clean = clean_phone_number(new_phone)
            if not phone_clean or len(phone_clean) != 12:
                messages.error(request, "Iltimos, to'g'ri O'zbekiston telefon raqamini kiriting (masalan: +998 90 123 45 67)!", extra_tags='phone')
            else:
                formatted_phone = f"+{phone_clean}"
                student.phone_number = formatted_phone
                student.save()
                log_action(student, "Telefon raqami o'zgartirildi", f"Yangi telefon: {formatted_phone}", request)
                messages.success(request, "Telefon raqamingiz muvaffaqiyatli yangilandi!", extra_tags='phone_success')
                return redirect('student_profile')

        elif form_type == 'change_password':
            old_password = request.POST.get('old_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')

            if not student.check_password(old_password):
                messages.error(request, "Eski parol noto‘g‘ri!", extra_tags='passwordd')
            elif new_password1 != new_password2:
                messages.error(request, "Yangi parollar bir xil emas!", extra_tags='passwordd')
            elif len(new_password1) < 8:
                messages.error(request, "Yangi parol kamida 8 ta belgidan iborat bo‘lishi kerak!", extra_tags='passwordd')
            else:
                student.set_password(new_password1)
                student.save()
                update_session_auth_hash(request, student)
                messages.success(request, "Parolingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='passwordd_img')
                return redirect('student_profile')

        elif form_type == 'upload_image':
            if 'profile_image' in request.FILES:
                image = request.FILES['profile_image']
                from main.validators import validate_image_file
                from django.core.exceptions import ValidationError
                try:
                    validate_image_file(image)
                except ValidationError as ve:
                    messages.error(request, ve.message, extra_tags='passwordd')
                    return redirect('student_profile')
                student.profile_image = image
                student.save()
                messages.success(request, "Rasmingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='passwordd_img')
                return redirect('student_profile')
            else:
                messages.error(request, "Rasm tanlanmadi.", extra_tags='passwordd')
                return redirect('student_profile')

    # Student guruhlari, fanlari va a'zolik ma'lumotlari
    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group', 'group__subject').prefetch_related('group__teachers').order_by('-joined_at')
    groups = [m.group for m in memberships]
    seen_subjects = set()
    subjects = []
    for g in groups:
        if g.subject and g.subject.id not in seen_subjects:
            seen_subjects.add(g.subject.id)
            subjects.append(g.subject)

    # Telegram bot link and username
    from main.telegram_service import get_bot_username, generate_telegram_link
    bot_username = get_bot_username()
    telegram_link = None
    if not student.telegram_chat_id:
        telegram_link = generate_telegram_link(student)

    return render(request, 'student-profile.html', {
        'student': student,
        'memberships': memberships,
        'groups': groups,
        'subjects': subjects,
        'telegram_link': telegram_link,
        'bot_username': bot_username,
    })



@login_required
def student_groups_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    # GroupStudentMembership orqali barcha guruhlar bilan qo‘shilish vaqtini olish
    memberships = GroupStudentMembership.objects.select_related('group').filter(student=student).prefetch_related('group__teachers')

    context = {
        'memberships': memberships,
        'student': student,
    }
    return render(request, 'student_group_list.html', context)


DAYS_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
DAY_NAMES = dict(DAYS_OF_WEEK)


@login_required
def student_schedule_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    groups = list(student.student_groups.all())
    group_ids = [g.id for g in groups]

    schedules = Schedule.objects.filter(group_id__in=group_ids).order_by('start_time')
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

        for day_key in DAYS_ORDER:
            vaqtlar = schedule_map.get((group.id, day_key), [])
            group_row['schedule_list'].append({
                'day': day_key,
                'day_name': DAY_NAMES[day_key],
                'vaqtlar': vaqtlar
            })

        jadval_data.append(group_row)

    context = {
        'jadval_data': jadval_data,
        'student': student
    }

    return render(request, 'student-dars-table.html', context)


@login_required
def student_quiz_list(request):
    student = request.user

    if student.role != 'student':
        return redirect('login')

    memberships = {m.group_id: m.joined_at for m in GroupStudentMembership.objects.filter(student=student)}
    if not memberships:
        return render(request, 'student-quiz-list.html', {'student': student, 'quiz_data': []})

    from django.db.models import Count
    quizzes = list(Quiz.objects.filter(group_id__in=memberships.keys()).select_related('group').annotate(total_questions=Count('questions', distinct=True)).distinct().order_by('-created_at'))
    results_map = {r.quiz_id: r for r in StudentQuizResult.objects.filter(student=student, quiz__in=quizzes).prefetch_related('answers__selected_answer')}

    quiz_data = []
    for quiz in quizzes:
        joined_at = memberships.get(quiz.group_id)
        if not joined_at or joined_at > quiz.created_at:
            continue

        result = results_map.get(quiz.id)
        total_questions = quiz.total_questions
        correct_count = 0
        score = None
        result_id = None
        score_percent = None

        if result:
            for answer in result.answers.all():
                if answer.selected_answer and answer.selected_answer.is_correct:
                    correct_count += 1

            result_id = result.id
            score = result.score
            if quiz.max_score:
                score_percent = round((score / quiz.max_score) * 100)

        quiz_data.append({
            'quiz': quiz,
            'total_questions': total_questions,
            'correct_count': correct_count if result else None,
            'score': score,
            'score_percent': score_percent,
            'result_id': result_id,
        })

    return render(request, 'student-quiz-list.html', {
        'student': student,
        'quiz_data': quiz_data,
    })


@login_required
def start_quiz(request, quiz_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    quiz = get_object_or_404(Quiz, id=quiz_id)

    # Guruh a'zoligi va qo'shilgan vaqtni tekshirish
    membership = GroupStudentMembership.objects.filter(student=student, group=quiz.group).first()
    if not membership or membership.joined_at > quiz.created_at:
        messages.error(request, "Siz ushbu testda qatnasha olmaysiz.")
        return redirect('student_quiz_list')

    existing_result = StudentQuizResult.objects.filter(student=student, quiz=quiz).first()

    if existing_result:
        if existing_result.quiz_last_updated >= quiz.updated_at:
            messages.info(request, "Siz bu testni bajargansiz.", extra_tags='quiz-info')
            return redirect('student_quiz_list')
        else:
            existing_result.delete()

    questions = quiz.questions.prefetch_related('answers')

    return render(request, 'student_quiz_start.html', {
        'quiz': quiz,
        'questions': questions,
        'student': student,
        'time_limit': quiz.time_limit,
    })


@login_required
@rate_limit(limit=10, period=60)
def submit_quiz(request, quiz_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    quiz = get_object_or_404(Quiz, id=quiz_id)

    # Guruh a'zoligi va qo'shilgan vaqtni tekshirish
    membership = GroupStudentMembership.objects.filter(student=student, group=quiz.group).first()
    if not membership or membership.joined_at > quiz.created_at:
        messages.error(request, "Siz ushbu testda qatnasha olmaysiz.")
        return redirect('student_quiz_list')

    existing_result = StudentQuizResult.objects.filter(student=student, quiz=quiz).prefetch_related('answers__selected_answer').first()

    if request.method == "GET":
        if existing_result and existing_result.quiz_last_updated >= quiz.updated_at:
            correct_count = 0
            for answer in existing_result.answers.all():
                if answer.selected_answer and answer.selected_answer.is_correct:
                    correct_count += 1
            total_questions = quiz.questions.count()
            score = existing_result.score
            score_percent = round((score / quiz.max_score) * 100) if quiz.max_score else 0

            return render(request, 'student_submit_quiz.html', {
                'student': student,
                'result': existing_result,
                'correct_count': correct_count,
                'total_questions': total_questions,
                'score': score,
                'score_percent': score_percent
            })
        return redirect('student_quiz_list')

    if request.method == "POST":
        if existing_result and existing_result.quiz_last_updated >= quiz.updated_at:
            correct_count = 0
            for answer in existing_result.answers.all():
                if answer.selected_answer and answer.selected_answer.is_correct:
                    correct_count += 1
            total_questions = quiz.questions.count()
            score = round((correct_count / total_questions) * quiz.max_score) if total_questions else 0
            score_percent = round((score / quiz.max_score) * 100) if quiz.max_score else 0

            return render(request, 'student_submit_quiz.html', {
                'student': student,
                'result': existing_result,
                'correct_count': correct_count,
                'total_questions': total_questions,
                'score': score,
                'score_percent': score_percent
            })

        if existing_result:
            existing_result.delete()

        questions = list(quiz.questions.all())
        selected_ids = []
        q_answer_map = {}
        for question in questions:
            sid = request.POST.get(f'question_{question.id}')
            if sid and str(sid).isdigit():
                sid_int = int(sid)
                selected_ids.append(sid_int)
                q_answer_map[question.id] = sid_int

        answers_by_id = Answer.objects.in_bulk(selected_ids)

        correct_count = 0
        student_answers_to_create = []

        result = StudentQuizResult.objects.create(
            student=student,
            quiz=quiz,
            score=0,
            quiz_last_updated=quiz.updated_at
        )

        for question in questions:
            selected_id = q_answer_map.get(question.id)
            selected_answer = answers_by_id.get(selected_id) if selected_id else None

            student_answers_to_create.append(StudentAnswer(
                result=result,
                question=question,
                selected_answer=selected_answer
            ))

            if selected_answer and selected_answer.is_correct:
                correct_count += 1

        StudentAnswer.objects.bulk_create(student_answers_to_create)

        total_questions = len(questions)
        score = round((correct_count / total_questions) * quiz.max_score) if total_questions else 0
        score_percent = round((score / quiz.max_score) * 100) if quiz.max_score else 0
        result.score = score
        result.save(update_fields=['score'])
        log_action(student, "Test Topshirildi", f"Talaba '{quiz.title}' testini topshirdi. Natija: {score}/{quiz.max_score} ({correct_count}/{total_questions} to'g'ri javob)", request)

        return render(request, 'student_submit_quiz.html', {
            'student': student,
            'result': result,
            'correct_count': correct_count,
            'total_questions': total_questions,
            'score': score,
            'score_percent': score_percent,
        })

    return redirect('student_quiz_list')


@login_required
def student_assignments_view(request):
    student = request.user

    if student.role != 'student':
        return redirect('login')

    # Guruh a'zoligini olib, qo‘shilgan vaqtni olish
    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_join_times = {m.group.id: m.joined_at for m in memberships}

    # Har bir guruh uchun, faqat guruhga qo‘shilgandan keyin yaratilgan topshiriqlarni olish
    if not group_join_times:
        assignments = Assignment.objects.none()
    else:
        q_filter = Q()
        for group_id, joined_at in group_join_times.items():
            q_filter |= Q(group_id=group_id, created_at__gte=joined_at)

        assignments = Assignment.objects.filter(q_filter)\
            .select_related('group', 'teacher')\
            .order_by('-created_at')

    # Student topshirgan assignmentlar
    submissions_qs = AssignmentSubmission.objects.filter(student=student)
    submissions = {s.assignment.id: s for s in submissions_qs}

    # Muddati o‘tganlar
    current_time = now()
    expired_ids = [a.id for a in assignments if a.deadline < current_time]

    return render(request, 'student_assignments.html', {
        'assignments': assignments,
        'submissions': submissions,
        'expired_ids': expired_ids,
        'student': student,
    })


@login_required
def submit_assignment(request, assignment_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    assignment = get_object_or_404(Assignment, id=assignment_id)

    # Guruh a'zoligi va qo'shilgan vaqtni tekshirish
    membership = GroupStudentMembership.objects.filter(student=student, group=assignment.group).first()
    if not membership or membership.joined_at > assignment.created_at:
        messages.error(request, "Siz ushbu guruh topshiriqlarida qatnasha olmaysiz.")
        return redirect('student_assignments')

    # Topshiriq muddati tekshiruvi
    if assignment.deadline < timezone.now():
        messages.error(request, "Ushbu topshiriqni yuklash muddati o'tib ketgan!")
        return redirect('student_assignments')

    if request.method == "POST" and request.FILES.get('file'):
        file_obj = request.FILES['file']
        from main.validators import validate_document_file
        from django.core.exceptions import ValidationError
        try:
            validate_document_file(file_obj)
        except ValidationError as ve:
            messages.error(request, ve.message)
            return redirect('student_assignments')

        # Avvalgi yuklangan topshiriq bo‘lsa, o‘chir
        AssignmentSubmission.objects.filter(assignment=assignment, student=student).delete()

        # Yangi topshiriqni saqlash
        sub = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=student,
            file=file_obj
        )
        log_action(student, "Topshiriq Topshirildi", f"Talaba '{assignment.title}' topshirig'iga javob yubordi. (Fayl: {file_obj.name}, ID: {sub.id})", request)
        messages.success(request, "Topshiriq muvaffaqiyatli yuborildi.")
        return redirect('student_assignments')

    return redirect('student_assignments')


@login_required
def student_payment_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    # O‘quvchi qaysi guruhlarga tegishli
    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_ids = [m.group.id for m in memberships]

    # To‘lov ma’lumotlari
    payments = list(StudentPayment.objects.filter(student=student, group_id__in=group_ids).select_related('group'))

    # Group payments by group_id in memory
    payments_by_group = {}
    for p in payments:
        payments_by_group.setdefault(p.group_id, []).append(p)

    # O'tgan kalendar oyi bo'yicha nishonni hisoblash (Dynamic Gamification Badges)
    import datetime
    now_dt = datetime.datetime.now()
    if now_dt.month == 1:
        prev_month_num = 12
    else:
        prev_month_num = now_dt.month - 1

    # Davomatlar - barcha guruhlar bo'yicha oldindan yuklash
    attendances = list(Attendance.objects.filter(student=student, group_id__in=group_ids, date__month=prev_month_num))
    attendances_by_group = {}
    for att in attendances:
        attendances_by_group.setdefault(att.group_id, []).append(att)

    # Fanlar bo'yicha testlar va topshiriqlar - oldindan yuklash
    quizzes = list(Quiz.objects.filter(group_id__in=group_ids, created_at__month=prev_month_num))
    quizzes_by_group = {}
    for q in quizzes:
        quizzes_by_group.setdefault(q.group_id, []).append(q)

    assignments = list(Assignment.objects.filter(group_id__in=group_ids, created_at__month=prev_month_num))
    assignments_by_group = {}
    for a in assignments:
        assignments_by_group.setdefault(a.group_id, []).append(a)

    # Test natijalari va topshiriq topshirilmalari - oldindan yuklash
    quiz_results = list(StudentQuizResult.objects.filter(student=student, quiz__in=quizzes))
    quiz_results_by_quiz = {r.quiz_id: r for r in quiz_results}

    submissions = list(AssignmentSubmission.objects.filter(student=student, assignment__in=assignments, grade__isnull=False))
    submissions_by_assignment = {s.assignment_id: s for s in submissions}

    # Har bir guruh uchun kurs va to‘lov ma’lumotlari
    group_infos = []
    for m in memberships:
        group = m.group
        try:
            payment_info = group.payment_info  # GroupPaymentInfo bilan bog‘liq OneToOne
        except GroupPaymentInfo.DoesNotExist:
            continue

        # O‘quvchi shu guruh uchun to‘lagan summa (lug'atdan)
        group_payments = payments_by_group.get(group.id, [])
        total_paid = sum(p.amount_paid for p in group_payments)

        # Davomat (lug'atdan)
        group_atts = attendances_by_group.get(group.id, [])
        total_att = len(group_atts)
        present_att = sum(1 for att in group_atts if att.status == 'present')
        attendance_rate = (present_att / total_att) if total_att > 0 else 1.0

        # Akademik natijalar (lug'atdan)
        group_quizzes = quizzes_by_group.get(group.id, [])
        group_assignments = assignments_by_group.get(group.id, [])

        scores = []
        for q in group_quizzes:
            res = quiz_results_by_quiz.get(q.id)
            if res:
                scores.append(res.score / q.max_score * 100 if q.max_score > 0 else 0)
            else:
                scores.append(0)
        for a in group_assignments:
            sub = submissions_by_assignment.get(a.id)
            if sub:
                scores.append(sub.grade / a.max_score * 100 if a.max_score > 0 else 0)
            else:
                scores.append(0)

        avg_score = sum(scores) / len(scores) if scores else 100.0

        badge = None
        if total_att > 0 or scores:
            if attendance_rate == 1.0 and avg_score >= 95.0:
                badge = {
                    'name': "Oltin Nishon (100% chegirma)",
                    'color': "#ffb000",
                    'icon': "fas fa-award",
                    'desc': f"O'tgan oyda davomat 100% va o'rtacha ball {round(avg_score)}%"
                }
            elif attendance_rate >= 0.95 and avg_score >= 85.0:
                badge = {
                    'name': "Kumush Nishon (50% chegirma)",
                    'color': "#00f2fe",
                    'icon': "fas fa-medal",
                    'desc': f"O'tgan oyda davomat {round(attendance_rate * 100)}% va o'rtacha ball {round(avg_score)}%"
                }
            elif attendance_rate >= 0.90 and avg_score >= 75.0:
                badge = {
                    'name': "Bronza Nishon (10% chegirma)",
                    'color': "#ff9f43",
                    'icon': "fas fa-trophy",
                    'desc': f"O'tgan oyda davomat {round(attendance_rate * 100)}% va o'rtacha ball {round(avg_score)}%"
                }

        # Calculate monthly debt breakdown
        now_dt = timezone.now()
        start_year = m.joined_at.year
        start_month = m.joined_at.month
        
        end_year = now_dt.year
        end_month = now_dt.month
        
        monthly_fee = payment_info.monthly_fee
        course_duration = payment_info.course_duration_months
        
        monthly_debts = []
        if monthly_fee > 0:
            curr_year = start_year
            curr_month = start_month
            count = 0
            
            MONTH_MAPPING = {
                1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
                5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
                9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
            }
            
            while count < course_duration:
                if (curr_year > end_year) or (curr_year == end_year and curr_month > end_month):
                    break
                    
                month_name = MONTH_MAPPING[curr_month]
                
                # How much paid for this specific month in this group
                paid_for_month = sum(p.amount_paid for p in group_payments if p.month == month_name)
                
                if paid_for_month < monthly_fee:
                    debt_amt = monthly_fee - paid_for_month
                    monthly_debts.append({
                        'month': month_name,
                        'year': curr_year,
                        'fee': monthly_fee,
                        'paid': paid_for_month,
                        'debt': debt_amt
                    })
                    
                curr_month += 1
                if curr_month > 12:
                    curr_month = 1
                    curr_year += 1
                count += 1

        sorted_group_payments = sorted(group_payments, key=lambda x: x.paid_at, reverse=True)

        group_infos.append({
            'group': group,
            'course_duration': payment_info.course_duration_months,
            'monthly_fee': payment_info.monthly_fee,
            'total_fee': payment_info.total_fee(),
            'payments': sorted_group_payments,
            'total_paid': total_paid,
            'remaining': payment_info.total_fee() - total_paid,
            'badge': badge,
            'monthly_debts': monthly_debts
        })

    context = {
        'student': student,
        'group_infos': group_infos,
        'online_payments_enabled': getattr(settings, 'ONLINE_PAYMENTS_ENABLED', False),
    }
    return render(request, 'student_payment.html', context)


import os
import json
from django.conf import settings
from django.http import Http404
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.timezone import now
from main.models import AIQuiz, AIQuestion, AIAnswer, StudentAIAnswer, StudentAIPlan

# 🚀 Yangi Rasmiy Google GenAI SDK drayverlari va Pydantic
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List


# --- 📐 1. GEMINI UCHUN QAT'IY PYDANTIC SXEMALARI ---

class QuizOptionSchema(BaseModel):
    text: str
    is_correct: bool


class QuizQuestionSchema(BaseModel):
    text: str
    correct_explanation: str
    options: List[QuizOptionSchema]


class QuizStructureSchema(BaseModel):
    title: str
    time_limit: int
    questions: List[QuizQuestionSchema]


class StudentPlanSchema(BaseModel):
    advice: str
    plan: str


# --- 🤖 2. UNIVERSAL GEMINI SDK CHAQIRUV FUNKSIYASI ---

def call_gemini_sdk(prompt, response_schema=None, temperature=0.4):
    """
    Yangi rasmiy google-genai SDK orqali Gemini modeliga xavfsiz va tezkor murojaat qilish.
    Agar response_schema berilsa, qat'iy JSON qaytaradi, aks holda Plain Text/Markdown.
    """
    import time
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Gemini API key is not configured.")

    # SDK Client tashkil qilish
    client = genai.Client(api_key=api_key)

    # Eng tezkor, barqaror va aqlli rasmiy model
    model_name = 'gemini-2.5-flash'

    config_args = {
        'temperature': temperature,
        'top_p': 0.95,
        'max_output_tokens': 8192,
    }

    # Agar Pydantic sxemasi uzatilgan bo'lsa, qat'iy formatlashni yoqamiz
    if response_schema:
        config_args['response_mime_type'] = "application/json"
        config_args['response_schema'] = response_schema

    config = types.GenerateContentConfig(**config_args)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
            except Exception as m_err:
                print(f"gemini-2.5-flash failed, attempting fallback to gemini-2.0-flash: {m_err}")
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt,
                    config=config
                )
            return response.text
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            # Vaqtincha 503 va resurs yetishmovchiligi xatolarini aylanib o'tish uchun biroz kutamiz
            time.sleep(1.5)


# --- 🛠 3. MOCK (FALLBACK) FUNKSIYALARI ---

def generate_mock_quiz(categories, level, num_questions=5):
    questions = []
    for i in range(1, num_questions + 1):
        questions.append({
            "text": f"'{categories}' mavzusi bo'yicha {i}-savol ({level} darajasi)?",
            "correct_explanation": f"{i}-savol uchun to'g'ri javob izohi. Mavzuni o'rganish lozim.",
            "options": [
                {"text": f"To'g'ri javob varianti A ({i})", "is_correct": True},
                {"text": f"Noto'g'ri javob B ({i})", "is_correct": False},
                {"text": f"Noto'g'ri javob C ({i})", "is_correct": False},
                {"text": f"Noto'g'ri javob D ({i})", "is_correct": False}
            ]
        })
    return {
        "title": f"{categories}",
        "time_limit": num_questions * 2,
        "questions": questions
    }


def generate_mock_feedback(score, max_score, title, level):
    percent = round((score / max_score) * 100) if max_score else 0
    if percent >= 80:
        return f"Ajoyib natija! Siz '{title}' mavzusini '{level}' darajada juda yaxshi o'zlashtiribsiz ({percent}%). Deyarli barcha savollarga to'g'ri javob berdingiz."
    elif percent >= 50:
        return f"Yaxshi harakat! Siz '{title}' mavzusini '{level}' darajada {percent}% natija bilan topshirdingiz."
    else:
        return f"Tushkunlikka tushmang! Siz '{title}' mavzusini '{level}' darajada sinab ko'rdingiz ({percent}%)."


def generate_mock_plan(student, quizzes_count, average_score):
    if average_score < 60:
        advice = f"Achchiq haqiqat: Natijangiz {average_score}%. Bu juda past! Dangasalikni bas qiling va bugundanoq harakatni boshlang."
    else:
        advice = f"Achchiq haqiqat: Natijangiz {average_score}%. Yomon emas, lekin mukammallikdan yiroqsiz. Bo'shashmang!"
    
    plan = (
        "1-kun: Grammatika (Tenses) takrorlash va 15 ta yangi so'z yodlash.\n"
        "2-kun: Listening mashqlari (TED Talks) - 15 daqiqa.\n"
        "3-kun: Reading - Kichik hikoya o'qish va tahlil qilish.\n"
        "4-kun: Speaking - Ayna qarshisida 10 daqiqa gapirish.\n"
        "5-kun: Writing - 'My goals' mavzusida insho yozish.\n"
        "6-kun: Vocabulary - Yangi so'zlarni jumlalarda ishlatish.\n"
        "7-kun: Haftalik test yechish va xatolarni tahlil qilish."
    )
    return advice, plan


import threading
ai_api_lock = threading.BoundedSemaphore(5)


@login_required
def ai_quiz_dashboard(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_quiz = AIQuiz.objects.filter(student=student, created_at__gte=today_start).first()
    today_quiz_created = today_quiz is not None

    quizzes = AIQuiz.objects.filter(student=student).order_by('-created_at')

    completed_quizzes = quizzes.filter(is_completed=True)
    total_quizzes_count = quizzes.count()
    completed_quizzes_count = completed_quizzes.count()

    total_score = sum(q.score or 0 for q in completed_quizzes)
    total_max_score = sum(q.max_score for q in completed_quizzes)
    average_percent = round((total_score / total_max_score) * 100) if total_max_score > 0 else 0

    best_quiz = None
    best_percent = 0
    for q in completed_quizzes:
        p = round(((q.score or 0) / q.max_score) * 100)
        if p > best_percent:
            best_percent = p
            best_quiz = q

    if request.method == "POST":
        if today_quiz_created:
            messages.warning(
                request,
                "Siz bugun kunlik AI test yaratish va bajarish huquqingizdan foydalandingiz. 1 kunda faqat 1 marta AI test bajara olasiz! Ertaga yangi test yaratishingiz mumkin."
            )
            return redirect('ai_quiz_dashboard')

        level = request.POST.get('level', 'beginner').strip().lower()
        num_questions = int(request.POST.get('num_questions', '5'))
        custom_category = request.POST.get('custom_category', '').strip()

        if not custom_category:
            messages.error(request, "Iltimos, test mavzusini kiriting.")
            return redirect('ai_quiz_dashboard')

        categories_str = custom_category

        if level == 'beginner':
            level_code = "A1-A2"
            level_display = "Boshlang'ich (A1-A2 darajasi)"
            level_instructions = (
                "DARAJA TALABLARI: A1-A2 (Boshlang'ich / Elementary).\n"
                "- Savollar asosiy tushunchalar, kundalik iboralar va fundamental qoidalarga asoslansin.\n"
                "- So'z boyligi va jumlalar sodda va to'g'ridan-to'g'ri bo'lsin."
            )
        elif level == 'intermediate':
            level_code = "B1-B2"
            level_display = "O'rta / O'rtadan yuqori (B1-B2 darajasi)"
            level_instructions = (
                "DARAJA TALABLARI: B1-B2 (O'rta va O'rtadan yuqori / Intermediate & Upper-Intermediate - CEFR B2 STANDARTI).\n"
                "- Savollar murakkab qoidalar (Mixed Conditionals, Passives, Modal verbs, Phrasal verbs, Dependent prepositions) va sabab-oqibatli mantiqqa asoslansin.\n"
                "- Barcha 4 ta variant ham mantiqan juda yaqin, chuqur o'ylantiradigan va asosli (plausible distractors) bo'lsin.\n"
                "- Kontekstual vaziyatlar va real hayotiy misollardan foydalanilsin."
            )
        else:
            level = 'advanced'
            level_code = "C1-C2"
            level_display = "Yuqori / Murakkab (C1-C2 darajasi)"
            level_instructions = (
                "DARAJA TALABLARI: C1-C2 (Yuqori, Professional va Ilmiy / Advanced & Mastery - CEFR C1-C2 STANDARTI).\n"
                "- Savollar nozik farqlar (subtle distinctions), Inversion, Cleft sentences, Subjunctive mood, akademik darajadagi leksika va qoidalarning istisnolariga asoslansin.\n"
                "- Savollar o'quvchining chuqur analitik va mantiqiy tafakkurini sinovdan o'tkazsin.\n"
                "- Noto'g'ri variantlar oddiy xato emas, balki yuqori darajada kuchli va nozik chalg'ituvchi (high-level distractors) bo'lsin."
            )

        prompt = f"""
        Siz professional xalqaro imtihonlar (CEFR, IELTS, DTM, SAT) tuzuvchi tajribali ekspert va metodistsiz.
        O'quvchi uchun mustaqil test topshiriqlarini tuzib bering.

        Mavzu: "{categories_str}"
        Talab qilinadigan savollar soni: ANIQ {num_questions} TA SAVOL TUZING (aynan {num_questions} ta savol bo'lishi shart).
        
        {level_instructions}

        MUHIM QOIDALAR:
        1. Har bir savolda aniq 4 ta variant (options) bo'lsin, ulardan faqat 1 tasi to'g'ri (is_correct: true), qolgan 3 tasi noto'g'ri (is_correct: false) bo'lsin.
        2. Agar mavzu chet tili (masalan, Ingliz tili) bo'lsa, savol matni va 4 ta varianti o'sha tilda bo'lsin. Ammo 'correct_explanation' (to'g'ri javob izohi) HAR DOIM mukammal, ravon va ilmiy O'ZBEK tilida bo'lishi shart.
        3. Agar mavzu aniq yoki tabiiy fanlar (Matematika, Fizika, Kimyo) bo'lsa, formulalarni standart LaTeX ($...$) ko'rinishida yozing.
        4. 'correct_explanation'da nima uchun aynan shu javob to'g'riligi va boshqa variantlar nima sababdan xatoligi ixcham va tushunarli tahlil qilinsin.
        5. 'time_limit' qiymatini har bir savol uchun 2 daqiqa hisobida butun son (daqiqa) sifatida belgilang ({num_questions * 2} daqiqa).
        6. 'title' qiymatiga mavzuning to'liq nomini bering ("{categories_str}").
        """

        # Concurrency control with generous timeout for large 20-question quizzes
        acquired = ai_api_lock.acquire(timeout=60)
        try:
            api_response = call_gemini_sdk(prompt, response_schema=QuizStructureSchema, temperature=0.4)
            quiz_data = json.loads(api_response)
        except Exception as e:
            print(f"--- Gemini SDK Quiz Error: {str(e)} ---")
            quiz_data = generate_mock_quiz(categories_str, level_display, num_questions)
            messages.warning(request, "AI bilan bog'lanishda navbat yoki xatolik yuz berdi. Namunaviy test yaratildi.")
        finally:
            if acquired:
                ai_api_lock.release()

        try:
            with transaction.atomic():
                quiz = AIQuiz.objects.create(
                    student=student,
                    title=quiz_data.get('title', categories_str)[:255],
                    categories=categories_str,
                    level=level,
                    max_score=100,
                    time_limit=quiz_data.get('time_limit', num_questions * 2)
                )
                for q_item in quiz_data.get('questions', []):
                    question = AIQuestion.objects.create(
                        quiz=quiz,
                        text=q_item.get('text', 'Savol matni'),
                        correct_explanation=q_item.get('correct_explanation', '')
                    )
                    for opt in q_item.get('options', []):
                        AIAnswer.objects.create(
                            question=question,
                            text=opt.get('text', 'Variant'),
                            is_correct=opt.get('is_correct', False)
                        )
            return redirect('ai_quiz_take', quiz_id=quiz.id)

        except Exception as db_err:
            print(f"--- Database Save Error: {str(db_err)} ---")
            messages.error(request, "Testni bazaga saqlashda ichki xatolik yuz berdi.")
            return redirect('ai_quiz_dashboard')

    context = {
        'student': student,
        'quizzes': quizzes,
        'total_quizzes_count': total_quizzes_count,
        'completed_quizzes_count': completed_quizzes_count,
        'average_percent': average_percent,
        'best_quiz': best_quiz,
        'best_percent': best_percent,
        'today_quiz_created': today_quiz_created,
        'today_quiz': today_quiz,
    }
    return render(request, 'student_ai_quiz_dashboard.html', context)


@login_required
def ai_quiz_take(request, quiz_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    quiz = get_object_or_404(AIQuiz, id=quiz_id, student=student)
    if quiz.is_completed:
        return redirect('ai_quiz_results', quiz_id=quiz.id)

    questions = quiz.questions.all().prefetch_related('answers')
    return render(request, 'student_ai_quiz_take.html', {
        'student': student,
        'quiz': quiz,
        'questions': questions
    })


@login_required
@rate_limit(limit=5, period=60)
def ai_quiz_submit(request, quiz_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    quiz = get_object_or_404(AIQuiz, id=quiz_id, student=student)
    if quiz.is_completed:
        return redirect('ai_quiz_results', quiz_id=quiz.id)

    if request.method == "POST":
        questions = list(quiz.questions.all())
        total_questions = len(questions)

        StudentAIAnswer.objects.filter(quiz=quiz).delete()
        detailed_results = []

        selected_ids = []
        q_answer_map = {}
        for question in questions:
            sid = request.POST.get(f'question_{question.id}')
            if sid and str(sid).isdigit():
                sid_int = int(sid)
                selected_ids.append(sid_int)
                q_answer_map[question.id] = sid_int

        answers_by_id = AIAnswer.objects.in_bulk(selected_ids)

        correct_count = 0
        student_answers_to_create = []

        with transaction.atomic():
            for question in questions:
                selected_id = q_answer_map.get(question.id)
                selected_answer = answers_by_id.get(selected_id) if selected_id else None

                student_answers_to_create.append(StudentAIAnswer(
                    quiz=quiz,
                    question=question,
                    selected_answer=selected_answer
                ))

                is_correct = selected_answer.is_correct if selected_answer else False
                if is_correct:
                    correct_count += 1

                status_text = "To'g'ri" if is_correct else "Noto'g'ri"
                detailed_results.append(
                    f"Savol: {question.text}\n"
                    f"O'quvchi javobi: {selected_answer.text if selected_answer else 'Javob berilmagan'}\n"
                    f"Holati: {status_text}\n"
                    f"To'g'ri izoh: {question.correct_explanation or 'Izoh mavjud emas'}\n"
                )

            StudentAIAnswer.objects.bulk_create(student_answers_to_create)

            score = round((correct_count / total_questions) * quiz.max_score) if total_questions else 0
            quiz.score = score
            quiz.is_completed = True
            quiz.submitted_at = now()
            quiz.save()
            log_action(student, "AI Test Topshirildi", f"Talaba '{quiz.title}' AI testini topshirdi. Natija: {score}/{quiz.max_score} ({correct_count}/{total_questions} to'g'ri)", request)

        score_percent = round((score / quiz.max_score) * 100) if quiz.max_score else 0
        detailed_results_str = "\n".join(detailed_results)

        # Plain text / Markdown feedback so'raymiz
        feedback_prompt = f"""
        Siz barcha fanlar bo'yicha o'quvchiga yordam beruvchi do'stona sun'iy intellekt repetitorsiz.
        O'quvchi o'zi uchun maxsus tuzilgan mustaqil testni topshirdi.

        Test tafsilotlari:
        Mavzu: {quiz.title}
        Tanlangan daraja: {quiz.get_level_display()}
        Natija: {quiz.score} / {quiz.max_score} (Foizda: {score_percent}%)

        Savollar va o'quvchining tanlagan javoblari:
        {detailed_results_str}

        Iltimos, o'quvchining natijasini tahlil qilib, o'zbek tilida batafsil tahliliy sharh (feedback) yozib bering.
        Markdown formatidan foydalaning (ro'yxat, muhim so'zlarni qalinlashtirish).
        Ohang har doim motivatsiya beruvchi va ijobiy bo'lsin.
        """
        try:
            ai_feedback = call_gemini_sdk(feedback_prompt)
        except Exception:
            ai_feedback = generate_mock_feedback(score, quiz.max_score, quiz.title, quiz.get_level_display())

        quiz.ai_feedback = ai_feedback
        quiz.save()
        return redirect('ai_quiz_results', quiz_id=quiz.id)

    return redirect('ai_quiz_dashboard')


@login_required
def ai_quiz_results(request, quiz_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    quiz = get_object_or_404(AIQuiz, id=quiz_id, student=student)
    if not quiz.is_completed:
        return redirect('ai_quiz_take', quiz_id=quiz.id)

    student_answers = StudentAIAnswer.objects.filter(quiz=quiz).select_related('question', 'selected_answer')
    answers_map = {sa.question_id: sa.selected_answer for sa in student_answers}

    questions_data = []
    for question in quiz.questions.all().prefetch_related('answers'):
        selected_answer = answers_map.get(question.id)
        questions_data.append({
            'question': question,
            'answers': question.answers.all(),
            'selected_answer': selected_answer,
            'is_correct': selected_answer.is_correct if selected_answer else False
        })

    score_percent = round(((quiz.score or 0) / quiz.max_score) * 100) if quiz.max_score else 0

    feedback_text = quiz.ai_feedback or ""
    try:
        data = json.loads(feedback_text)
        if isinstance(data, dict) and 'feedback' in data:
            feedback_text = data['feedback']
    except (json.JSONDecodeError, TypeError):
        pass

    return render(request, 'student_ai_quiz_results.html', {
        'student': student,
        'quiz': quiz,
        'questions_data': questions_data,
        'score_percent': score_percent,
        'feedback_text': feedback_text
    })


@login_required
def student_ai_plan(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    ai_plan = StudentAIPlan.objects.filter(student=student).first()

    if request.method == "POST":
        if ai_plan and ai_plan.updated_at.date() == timezone.now().date():
            messages.warning(request, "Siz bugun AI Maslahatchi rejani yangilab bo'ldingiz. 1 kunda faqat 1 marta reja yangilash mumkin!")
            return redirect('student_ai_plan')

        completed_quizzes = AIQuiz.objects.filter(student=student, is_completed=True)
        total_quizzes = completed_quizzes.count()

        total_score = sum(q.score or 0 for q in completed_quizzes)
        average_score = round(total_score / total_quizzes) if total_quizzes > 0 else 0

        quiz_history = []
        for q in completed_quizzes.order_by('-created_at')[:10]:
            quiz_history.append(f"- Mavzu: {q.title}, Daraja: {q.get_level_display()}, Natija: {q.score}%")

        history_str = "\n".join(quiz_history) if quiz_history else "Hech qanday test topshirilmagan."

        prompt = f"""
        Siz o'quvchini dangasalikdan qutqarish va uni o'qishga majburlash uchun juda qattiqqo'l, o'ta jiddiy, to'g'ri so'zlovchi va o'ta lakonik (qisqa va lo‘nda gapiradigan) sun'iy intellekt repetitorsiz.
        Maqsadingiz o'quvchining natijalaridan kelib chiqib, unga qattiq va ta'sirchan tanbeh (achchiq haqiqat) berish hamda kelgusi 7 kun uchun lo‘nda, aniq reja tuzib berish.

        O'quvchi ma'lumotlari:
        Ism: {student.first_name} {student.last_name}
        Topshirgan AI testlari soni: {total_quizzes} ta
        O'rtacha natijasi: {average_score}%
        Oxirgi topshirgan testlari:
        {history_str}

        Formatlash qoidalari:
        1. 'advice' (achchiq haqiqat) maydoni:
           - Maksimal 3-4 ta ta'sirchan gapdan iborat bo‘lsin.
           - Juda o‘tkir, jiddiy, ogohlantiruvchi va motivatsiya beruvchi bo‘lsin.
           - Dangasalikni qattiq tanqid qiling (agar ball past bo'lsa) yoki bo'shashmaslikni talab qiling (agar ball baland bo'lsa). Ortiqcha maqtov yoki uzun kirish so'zlari bo'lmasin.
        2. 'plan' (7 kunlik reja) maydoni:
           - Kelgusi 7 kunlik reja juda qisqa, har bir kun uchun faqat 1 tadan aniq, bajariladigan va lo‘nda ingliz tili topshirig‘i bo‘lsin.
           - Masalan: "1-kun: Grammatika (Tenses) takrorlash va 15 daqiqa o'qish.", "2-kun: ..." ko‘rinishida bo‘lsin.
           - Har bir kun uchun yozilgan matn 1 qatordan oshmasin.
        3. Sharh va rejalar aniq o'zbek tilida shakllansin.
        """

        try:
            # Reja tuzish uchun StudentPlanSchema Pydantic modelidan foydalanamiz
            api_response = call_gemini_sdk(prompt, response_schema=StudentPlanSchema)
            plan_data = json.loads(api_response)
            advice = plan_data.get('advice', '')
            plan = plan_data.get('plan', '')
        except Exception as e:
            print(f"--- Gemini SDK Plan Error: {str(e)} ---")
            advice_mock, plan_mock = generate_mock_plan(student, total_quizzes, average_score)
            advice = advice_mock
            plan = plan_mock
            messages.warning(request, "AI bilan bog'lanishda muammo yuz berdi. Namunaviy reja yuklandi.")

        if ai_plan:
            ai_plan.advice = advice
            ai_plan.plan = plan
            ai_plan.save()
        else:
            ai_plan = StudentAIPlan.objects.create(
                student=student,
                advice=advice,
                plan=plan
            )
        messages.success(request, "AI maslahati va 7 kunlik reja muvaffaqiyatli yangilandi!")
        return redirect('student_ai_plan')

    return render(request, 'student_ai_plan.html', {
        'student': student,
        'ai_plan': ai_plan
    })


@login_required
def student_group_detail(request, group_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    group = get_object_or_404(Group, id=group_id, students=student)
    lessons = group.lessons.all().order_by('-date', '-created_at')

    # Reyting (Leaderboard) hisoblash - Bulk Aggregation
    leaderboard = []
    quizzes = list(Quiz.objects.filter(group=group))
    assignments = list(Assignment.objects.filter(group=group))
    students = list(group.students.all())
    student_ids = [s.id for s in students]

    total_quiz_max = sum(q.max_score for q in quizzes)
    total_hw_max = sum(a.max_score for a in assignments)

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

    for s in students:
        total_quiz_score = quiz_score_map.get(s.id, 0)
        avg_quiz_percent = (total_quiz_score / total_quiz_max * 100) if total_quiz_max > 0 else None

        total_hw_score = hw_score_map.get(s.id, 0)
        avg_hw_percent = (total_hw_score / total_hw_max * 100) if total_hw_max > 0 else None

        total_att = att_total_map.get(s.id, 0)
        present_att = att_present_map.get(s.id, 0)
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
            'student': s,
            'avg_quiz': avg_quiz_percent,
            'avg_hw': avg_hw_percent,
            'attendance': attendance_rate,
            'overall_score': round(overall_score, 1)
        })

    # Sort leaderboard by overall_score descending
    leaderboard = sorted(leaderboard, key=lambda x: x['overall_score'], reverse=True)

    my_attendances = Attendance.objects.filter(student=student, group=group).order_by('-date')
    my_total_att = my_attendances.count()
    my_present_att = my_attendances.filter(status='present').count()
    my_absent_att = my_attendances.filter(status='absent').count()
    my_att_rate = (my_present_att / my_total_att * 100) if my_total_att > 0 else 100

    return render(request, 'student_group_detail.html', {
        'group': group,
        'lessons': lessons,
        'leaderboard': leaderboard,
        'student': student,
        'my_attendances': my_attendances,
        'my_total_att': my_total_att,
        'my_present_att': my_present_att,
        'my_absent_att': my_absent_att,
        'my_att_rate': round(my_att_rate, 1),
    })


@login_required
def student_media_gallery(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    groups = student.student_groups.all()
    videos = GroupVideo.objects.filter(group__in=groups).select_related('group', 'teacher').order_by('-created_at')

    return render(request, 'student_media_gallery.html', {
        'student': student,
        'videos': videos,
        'groups': groups
    })


# ==========================================
# 🎓 STUDENT DTM MOCK EXAM VIEWS
# ==========================================
from main.models import DTMExam, DTMRegistration, StudentDTMExamResult

@login_required
def student_dtm_list(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    # Faol DTM imtihonlari
    active_exams = DTMExam.objects.filter(is_active=True).order_by('-exam_date')
    
    # Har bir imtihon uchun talabaning ro'yxatdan o'tish statusi
    exams_data = []
    now = timezone.now()

    for exam in active_exams:
        reg = DTMRegistration.objects.filter(student=student, exam=exam).select_related('result').first()
        
        status = "not_registered"
        result = None
        booklet_number = None
        booklet_file = None

        if reg:
            status = "registered"
            booklet_number = reg.booklet_number
            booklet_file = reg.booklet_file.url if reg.booklet_file else None
            if hasattr(reg, 'result'):
                status = "completed"
                result = reg.result
        else:
            if now > exam.registration_deadline:
                status = "deadline_passed"

        exams_data.append({
            'exam': exam,
            'status': status,
            'registration': reg,
            'result': result,
            'booklet_number': booklet_number,
            'booklet_file': booklet_file
        })

    return render(request, 'student_dtm_list.html', {
        'student': student,
        'exams_data': exams_data,
        'now': now
    })


@login_required
def student_dtm_register(request, exam_id):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    exam = get_object_or_404(DTMExam, id=exam_id, is_active=True)
    
    # Ro'yxatdan o'tish muddatini tekshirish
    if timezone.now() > exam.registration_deadline:
        messages.error(request, "Ushbu imtihonga ro'yxatdan o'tish muddati tugagan!")
        return redirect('student_dtm_list')

    # Oldin ro'yxatdan o'tgan bo'lsa
    if DTMRegistration.objects.filter(student=student, exam=exam).exists():
        messages.warning(request, "Siz ushbu imtihonga ro'yxatdan o'tib bo'lgansiz.")
        return redirect('student_dtm_list')

    subjects = ["Matematika", "Fizika", "Kimyo", "Biologiya", "Ingliz tili", "Ona tili", "Tarix", "Geografiya"]

    if request.method == 'POST':
        block1 = request.POST.get('block1_subject')
        block2 = request.POST.get('block2_subject')
        take_compulsory = request.POST.get('take_compulsory') == 'on'

        if block1 == block2:
            messages.error(request, "1-blok va 2-blok fanlari bir xil bo'lishi mumkin emas!")
        elif block1 and block2:
            reg = DTMRegistration.objects.create(
                student=student,
                exam=exam,
                block1_subject=block1,
                block2_subject=block2,
                take_compulsory=take_compulsory
            )
            log_action(student, "DTMga Ro'yxatdan O'tildi", f"Talaba '{exam.title}' imtihoniga ro'yxatdan o'tdi. (Fani: {block1} & {block2}, ID: {reg.id})", request)
            messages.success(request, f"{exam.title} imtihoniga muvaffaqiyatli yozildingiz! Imtihondan oldin admin sizga savollar varaqasini yuklaydi.")
            return redirect('student_dtm_list')
        else:
            messages.error(request, "Iltimos, blok fanlarini tanlang!")

    return render(request, 'student_dtm_register.html', {
        'exam': exam,
        'subjects': subjects
    })


@login_required
def student_subjects_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_ids = [m.group_id for m in memberships]
    
    groups = Group.objects.filter(id__in=group_ids).select_related('subject').prefetch_related('teachers')
    
    subjects_data = []
    seen_subject_ids = set()

    for group in groups:
        if group.subject and group.subject.id not in seen_subject_ids:
            seen_subject_ids.add(group.subject.id)
            
            materials = SubjectMaterial.objects.filter(subject=group.subject).order_by('-created_at')
            books = Book.objects.filter(subject=group.subject).order_by('-created_at')
            teachers = group.teachers.all()
            
            subjects_data.append({
                'subject': group.subject,
                'group': group,
                'teachers': teachers,
                'materials': materials,
                'books': books
            })

    return render(request, 'student-fanlar.html', {
        'student': student,
        'subjects_data': subjects_data
    })


@login_required
def disconnect_telegram(request):
    if request.method == 'POST':
        user = request.user
        user.telegram_chat_id = None
        user.telegram_token = None
        user.telegram_otp_code = None
        user.telegram_otp_created_at = None
        user.save()
        log_action(user, "Telegram Uzildi", "Foydalanuvchi Telegram bot ulanishini uzdi.", request)
        messages.success(request, "Telegram bot ulanishi muvaffaqiyatli uzildi.")
    if request.user.role == 'teacher':
        return redirect('teacher_profile')
    return redirect('student_profile')


import random
from django.utils import timezone

@login_required
def generate_telegram_otp_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': "Faqat POST so'rovi qabul qilinadi."}, status=400)
    
    user = request.user
    otp_code = f"{random.randint(100000, 999999)}"
    user.telegram_otp_code = otp_code
    user.telegram_otp_created_at = timezone.now()
    user.save()
    
    return JsonResponse({
        'status': 'success',
        'otp_code': otp_code,
        'expires_in': 60
    })

# @login_required
# def student_simulations_view(request):
#     return render(request, 'simulations_list.html', {
#         'base_template': 'basestudent.html'
#     })


@login_required
def student_book_flipbook_view(request, book_id):
    student = request.user
    book = get_object_or_404(Book, id=book_id)
    subject = book.subject
    
    # Security: check if student has a membership in any group with this subject (or if user is teacher/admin)
    if student.role == 'student':
        memberships = GroupStudentMembership.objects.filter(student=student, group__subject=subject)
        if not memberships.exists():
            messages.error(request, "Sizga ushbu kitobni o'qishga ruxsat berilmagan.")
            return redirect('student_home')
    elif student.role == 'teacher':
        if subject not in student.subjects.all():
            messages.error(request, "Sizga ushbu kitobni o'qishga ruxsat berilmagan.")
            return redirect('teacher_home')
    elif student.role not in ['admin', 'subadmin']:
        return redirect('login')

    return render(request, 'student_book_flipbook.html', {
        'book': book
    })


