from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from main.models import Quiz, Group, StudentQuizResult, Answer, StudentAnswer, Schedule, DAYS_OF_WEEK, Assignment, \
    AssignmentSubmission, CustomUser, GroupStudentMembership, StudentPayment, GroupPaymentInfo
from django.contrib.auth import update_session_auth_hash
from collections import OrderedDict
from django.utils.timezone import now
from django.db.models import Q



def get_student_level_among_group(student):
    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_ids = [m.group.id for m in memberships]

    # Barcha o‘quvchilar (shu guruhlarga tegishli)
    all_memberships = GroupStudentMembership.objects.filter(group_id__in=group_ids).select_related('student', 'group')

    student_join_dates = {}
    for m in all_memberships:
        sid = m.student.id
        gid = m.group.id
        if sid not in student_join_dates:
            student_join_dates[sid] = {}
        student_join_dates[sid][gid] = m.joined_at

    students = CustomUser.objects.filter(id__in=student_join_dates.keys(), role='student').distinct()

    good = average = weak = 0
    student_percent = None

    for s in students:
        join_dates = student_join_dates[s.id]
        student_quizzes = Quiz.objects.none()
        student_assignments = Assignment.objects.none()

        for group_id, joined_at in join_dates.items():
            student_quizzes |= Quiz.objects.filter(group_id=group_id, created_at__gte=joined_at)
            student_assignments |= Assignment.objects.filter(group_id=group_id, created_at__gte=joined_at)

        quiz_score = StudentQuizResult.objects.filter(
            student=s, quiz__in=student_quizzes
        ).aggregate(Sum('score'))['score__sum'] or 0

        assign_score = AssignmentSubmission.objects.filter(
            student=s, assignment__in=student_assignments,
            grade__isnull=False
        ).aggregate(Sum('grade'))['grade__sum'] or 0

        student_total_max = (
            student_quizzes.aggregate(Sum('max_score'))['max_score__sum'] or 0
        ) + (
            student_assignments.aggregate(Sum('max_score'))['max_score__sum'] or 0
        )

        if student_total_max == 0:
            continue

        percent = (quiz_score + assign_score) / student_total_max * 100

        if s == student:
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

    return {
        'total': students.count(),
        'good': good,
        'average': average,
        'weak': weak,
        'student_level': level
    }



from django.db.models import Sum

def get_top_students(current_student):
    memberships = GroupStudentMembership.objects.select_related('student', 'group')

    student_scores = []
    seen_students = set()

    for m in memberships:
        student = m.student
        if student.id in seen_students or student.role != 'student':
            continue
        seen_students.add(student.id)

        # O‘quvchining guruhdagi barcha topshiriq va testlari
        student_memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')

        all_assignments = Assignment.objects.none()
        all_quizzes = Quiz.objects.none()

        for sm in student_memberships:
            group_id = sm.group.id
            joined_at = sm.joined_at

            group_assignments = Assignment.objects.filter(group_id=group_id, created_at__gte=joined_at)
            group_quizzes = Quiz.objects.filter(group_id=group_id, created_at__gte=joined_at)

            all_assignments |= group_assignments
            all_quizzes |= group_quizzes

        # ✅ O‘quvchining to‘plagan ballari
        assign_score = AssignmentSubmission.objects.filter(
            student=student,
            assignment__in=all_assignments,
            grade__isnull=False
        ).aggregate(Sum('grade'))['grade__sum'] or 0

        quiz_score = StudentQuizResult.objects.filter(
            student=student,
            quiz__in=all_quizzes
        ).aggregate(Sum('score'))['score__sum'] or 0

        total_score = assign_score + quiz_score

        # ✅ Maksimal ball
        max_assign_score = all_assignments.aggregate(Sum('max_score'))['max_score__sum'] or 0
        max_quiz_score = all_quizzes.aggregate(Sum('max_score'))['max_score__sum'] or 0

        total_max_score = max_assign_score + max_quiz_score

        # ✅ Foiz hisoblash
        if total_max_score == 0:
            percentage = 0
        else:
            percentage = round((total_score / total_max_score) * 100, 2)

        student_scores.append({
            'student': student,
            'score_percent': percentage
        })

    # Reyting qilish
    sorted_scores = sorted(student_scores, key=lambda x: x['score_percent'], reverse=True)
    for idx, s in enumerate(sorted_scores, 1):
        s['rank'] = idx

    top_10 = sorted_scores[:10]
    student_place = next((s for s in sorted_scores if s['student'] == current_student), None)

    return top_10, student_place





@login_required
def student_home_view(request):
    student = request.user
    if student.role != 'student':
        return redirect('login')

    memberships = GroupStudentMembership.objects.filter(student=student).select_related('group')
    group_joined_times = {m.group.id: m.joined_at for m in memberships}
    group_ids = list(group_joined_times.keys())

    # Faqat guruhga qo‘shilgan vaqtdan keyin yaratilgan assignments va quizzes
    assignments = Assignment.objects.none()
    quizzes = Quiz.objects.none()

    for group_id, joined_at in group_joined_times.items():
        assignments |= Assignment.objects.filter(group_id=group_id, created_at__gte=joined_at)
        quizzes |= Quiz.objects.filter(group_id=group_id, created_at__gte=joined_at)

    # Statistika: foizlar
    total_assignments = assignments.count()
    completed_assignments = AssignmentSubmission.objects.filter(
        student=student,
        assignment__in=assignments
    ).count()

    total_quizzes = quizzes.count()
    completed_quizzes = StudentQuizResult.objects.filter(
        student=student,
        quiz__in=quizzes
    ).count()

    assignment_completion_percent = round((completed_assignments / total_assignments) * 100, 1) if total_assignments > 0 else 0
    assignment_missing_percent = round(100 - assignment_completion_percent, 1) if total_assignments > 0 else 0

    quiz_completion_percent = round((completed_quizzes / total_quizzes) * 100, 1) if total_quizzes > 0 else 0
    quiz_missing_percent = round(100 - quiz_completion_percent, 1) if total_quizzes > 0 else 0

    # Reyting va daraja: get_top_students va get_student_level_among_group aynan shu talablarga mos yozilgan
    top_students, student_place = get_top_students(student)
    level_info = get_student_level_among_group(student)

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
        'has_assignments': total_assignments > 0,
        'has_quizzes': total_quizzes > 0,
    }

    return render(request, 'student_home.html', context)


@login_required
def student_profile_view(request):
    student = request.user

    if student.role != 'student':
        return redirect('login')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'change_password':
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

        elif form_type == 'upload_image':
            if 'profile_image' in request.FILES:
                image = request.FILES['profile_image']
                student.profile_image = image
                student.save()
                messages.success(request, "Rasmingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='passwordd_img')
            else:
                messages.error(request, "Rasm tanlanmadi.", extra_tags='passwordd')

    return render(request, 'student-profile.html', {'student': student,})


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

    groups = student.student_groups.all()
    jadval_data = []

    for group in groups:
        group_row = {
            'id': group.id,
            'name': group.name,
            'schedule_list': []
        }

        for day_key in DAYS_ORDER:
            darslar = Schedule.objects.filter(group=group, day=day_key).order_by('start_time')
            vaqtlar = [
                f"{dars.start_time.strftime('%H:%M')} - {dars.end_time.strftime('%H:%M')}"
                for dars in darslar
            ]
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

    groups = student.student_groups.all()
    quizzes = Quiz.objects.filter(group__in=groups).distinct().order_by('-created_at')

    quiz_data = []

    for quiz in quizzes:
        # O'quvchi bu quiz guruhiga qachon qo'shilganini topamiz
        membership = GroupStudentMembership.objects.filter(
            group=quiz.group,
            student=student
        ).first()

        # Agar umuman membership yo'q bo‘lsa yoki quiz yaratilib bo‘lgandan keyin qo‘shilmagan bo‘lsa – o'tkazib yuboramiz
        if not membership or membership.joined_at > quiz.created_at:
            continue

        result = StudentQuizResult.objects.filter(student=student, quiz=quiz).first()

        total_questions = quiz.questions.count()
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

            if quiz.max_score:  # max_score mavjud bo‘lsa foizni hisoblaymiz
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

    quiz = get_object_or_404(Quiz, id=quiz_id)

    # Foydalanuvchi avval bu testni bajarganmi?
    existing_result = StudentQuizResult.objects.filter(student=student, quiz=quiz).first()

    if existing_result:
        # Agar testni bajargan bo‘lsa va u test tahrirlanmagan bo‘lsa — natijaga yo‘naltiramiz
        if existing_result.quiz_last_updated >= quiz.updated_at:
            messages.info(request, "Siz bu testni  bajargansiz.", extra_tags='quiz-info')
            return redirect('student_quiz_list')
        else:
            # Aks holda test tahrirlangan — avvalgi natijani o‘chiramiz
            existing_result.delete()

    # Testni boshlash sahifasi (savollarni ko‘rsatamiz)
    questions = quiz.questions.prefetch_related('answers')

    return render(request, 'student_quiz_start.html', {
        'quiz': quiz,
        'questions': questions,
        'student': student,
        'time_limit': quiz.time_limit,
    })



@login_required
def submit_quiz(request, quiz_id):
    student = request.user
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if request.method == "POST":
        existing_result = StudentQuizResult.objects.filter(student=student, quiz=quiz).first()
        if existing_result and existing_result.quiz_last_updated >= quiz.updated_at:
            # Eski natija mavjud va test o‘zgarmagan — natijani ko‘rsatamiz
            correct_count = 0
            for answer in existing_result.answers.all():
                if answer.selected_answer and answer.selected_answer.is_correct:
                    correct_count += 1
            total_questions = quiz.questions.count()
            score = round((correct_count / total_questions) * quiz.max_score) if total_questions else 0

            return render(request, 'student_submit_quiz.html', {
                'student': student,
                'result': existing_result,
                'correct_count': correct_count,
                'total_questions': total_questions,
                'score': score
            })

        # Eski natijani o‘chirish
        if existing_result:
            existing_result.delete()

        correct_count = 0
        result = StudentQuizResult.objects.create(
            student=student,
            quiz=quiz,
            score=0,
            quiz_last_updated=quiz.updated_at
        )

        for question in quiz.questions.all():
            selected_id = request.POST.get(f'question_{question.id}')
            selected_answer = Answer.objects.filter(id=selected_id).first()

            StudentAnswer.objects.create(
                result=result,
                question=question,
                selected_answer=selected_answer
            )

            if selected_answer and selected_answer.is_correct:
                correct_count += 1

        total_questions = quiz.questions.count()
        score = round((correct_count / total_questions) * quiz.max_score) if total_questions else 0
        score_percent = round((score / quiz.max_score) * 100) if quiz.max_score else 0
        result.score = score
        result.save()

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
    assignment = get_object_or_404(Assignment, id=assignment_id)
    student = request.user

    if request.method == "POST" and request.FILES.get('file'):
        # Avvalgi yuklangan topshiriq bo‘lsa, o‘chir
        AssignmentSubmission.objects.filter(assignment=assignment, student=student).delete()

        # Yangi topshiriqni saqlash
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=student,
            file=request.FILES['file']
        )
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
    payments = StudentPayment.objects.filter(student=student, group_id__in=group_ids).select_related('group')

    # Har bir guruh uchun kurs va to‘lov ma’lumotlari
    group_infos = []
    for m in memberships:
        group = m.group
        try:
            payment_info = group.payment_info  # GroupPaymentInfo bilan bog‘liq OneToOne
        except GroupPaymentInfo.DoesNotExist:
            continue

        # O‘quvchi shu guruh uchun to‘lagan summa
        total_paid = payments.filter(group=group).aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

        group_infos.append({
            'group': group,
            'course_duration': payment_info.course_duration_months,
            'monthly_fee': payment_info.monthly_fee,
            'total_fee': payment_info.total_fee(),
            'payments': payments.filter(group=group).order_by('-paid_at'),
            'total_paid': total_paid,
            'remaining': payment_info.total_fee() - total_paid
        })

    context = {
        'student': student,
        'group_infos': group_infos
    }
    return render(request, 'student_payment.html', context)