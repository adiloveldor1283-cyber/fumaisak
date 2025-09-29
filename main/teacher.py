from datetime import timedelta

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.db.models import Count

from . import student
from .models import Group, CustomUser, Schedule, Quiz, Question, Answer, StudentQuizResult, Assignment, Attendance, \
    AssignmentSubmission, GroupStudentMembership
from django.shortcuts import redirect


# O'qituvchiga tegishli guruhlardagi o'quvchilarni olish
def get_teacher_students(teacher):
    groups = teacher.teachers_groups.all()
    return CustomUser.objects.filter(student_groups__in=groups, role='student').distinct()

# Talabalarni kategoriyalash – faollikka qarab

def categorize_students(teacher):
    students = get_teacher_students(teacher)
    quizzes = Quiz.objects.filter(teacher=teacher)
    assignments = Assignment.objects.filter(teacher=teacher)

    good, average, weak = [], [], []
    student_levels = {}

    total_max_score = 0
    student_scores = {}

    for student in students:
        quiz_score_sum = 0
        assign_score_sum = 0
        student_total_max = 0

        for quiz in quizzes:
            # Agar student quizdan oldin guruhga qo‘shilgan bo‘lsa
            if GroupStudentMembership.objects.filter(
                student=student,
                group=quiz.group,
                joined_at__lte=quiz.created_at
            ).exists():
                result = StudentQuizResult.objects.filter(student=student, quiz=quiz).first()
                if result:
                    quiz_score_sum += result.score
                student_total_max += quiz.max_score

        for assignment in assignments:
            if GroupStudentMembership.objects.filter(
                student=student,
                group=assignment.group,
                joined_at__lte=assignment.created_at
            ).exists():
                submission = AssignmentSubmission.objects.filter(
                    student=student, assignment=assignment, grade__isnull=False
                ).first()
                if submission:
                    assign_score_sum += submission.grade
                student_total_max += assignment.max_score

        total_score = quiz_score_sum + assign_score_sum
        if student_total_max == 0:
            continue  # Bu o‘quvchi uchun baholashga mos topshiriqlar yo‘q

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

    return {
        'total': students.count(),
        'good': good,
        'average': average,
        'weak': weak,
        'student_levels': student_levels
    }


@login_required
def teacher_home_view(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    stats = categorize_students(teacher)
    # O'qituvchiga tegishli quiz va assignmentlar
    teacher_quizzes = Quiz.objects.filter(teacher=teacher)
    teacher_assignments = Assignment.objects.filter(teacher=teacher)

    # O'qituvchining o'quvchilari
    students = get_teacher_students(teacher)
    student_count = students.count()

    # Umumiy imkoniyatlar (barcha o'quvchilar har bir test/topshiriqni topshirishi mumkin)
    total_assignment_opportunities = teacher_assignments.count() * student_count
    total_quiz_opportunities = teacher_quizzes.count() * student_count

    # Haqiqiy topshirilganlar soni
    completed_assignments = 0
    for assignment in teacher_assignments:
        for student in students:
            if GroupStudentMembership.objects.filter(
                student=student,
                group=assignment.group,
                joined_at__lte=assignment.created_at
            ).exists():
                if AssignmentSubmission.objects.filter(assignment=assignment, student=student).exists():
                    completed_assignments += 1

    completed_quizzes = 0
    for quiz in teacher_quizzes:
        for student in students:
            if GroupStudentMembership.objects.filter(
                student=student,
                group=quiz.group,
                joined_at__lte=quiz.created_at
            ).exists():
                if StudentQuizResult.objects.filter(quiz=quiz, student=student).exists():
                    completed_quizzes += 1

    total_assignment_opportunities = 0
    total_quiz_opportunities = 0

    for assignment in teacher_assignments:
        for student in students:
            if GroupStudentMembership.objects.filter(
                student=student,
                group=assignment.group,
                joined_at__lte=assignment.created_at
            ).exists():
                total_assignment_opportunities += 1

    for quiz in teacher_quizzes:
        for student in students:
            if GroupStudentMembership.objects.filter(
                student=student,
                group=quiz.group,
                joined_at__lte=quiz.created_at
            ).exists():
                total_quiz_opportunities += 1


    # Foizlarni hisoblash
    assignment_completion_percent = (
        (completed_assignments / total_assignment_opportunities) * 100
        if total_assignment_opportunities > 0 else 0
    )
    quiz_completion_percent = (
        (completed_quizzes / total_quiz_opportunities) * 100
        if total_quiz_opportunities > 0 else 0
    )
    teacher_groups = Group.objects.filter(teachers=teacher)
    students = CustomUser.objects.filter(student_groups__in=teacher_groups).distinct()

    context = {
        'teacher': teacher,
        'students': students,
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


@login_required
def teacher_profile_view(request):
    teacher = request.user

    if teacher.role != 'teacher':
        return redirect('login')

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
                teacher.profile_image = image
                teacher.save()
                messages.success(request, "Rasmingiz muvaffaqiyatli o‘zgartirildi!", extra_tags='password_img')
            else:
                messages.error(request, "Rasm tanlanmadi.", extra_tags='password')

    return render(request, 'teacher-profile.html', {'teacher': teacher,})

@login_required
def my_student_view(request):
    teacher = request.user

    if teacher.role != 'teacher':
        return redirect('login')

    teacher_groups = Group.objects.filter(teachers=teacher)

    students = CustomUser.objects.filter(student_groups__in=teacher_groups).distinct()

    context = {'students': students, 'teacher': teacher,}
    return render(request, 'teacher_students_list.html', context)

@login_required
def my_groups_view(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    groups = teacher.teachers_groups.all()

    return render(request, 'teacher_group_list.html', {'groups': groups, 'teacher': teacher,})

@login_required
def group_detail_view(request, group_id):

    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    group = get_object_or_404(Group, id=group_id)

    if request.user not in group.teachers.all():
        return render(request, 'teacher_group_list.html')

    students = group.students.all()

    return render(request, 'group_detail.html', {'group': group, 'students': students, 'teacher': teacher,})


DAYS_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
DAY_NAMES = {
    'monday': 'Dushanba',
    'tuesday': 'Seshanba',
    'wednesday': 'Chorshanba',
    'thursday': 'Payshanba',
    'friday': 'Juma',
    'saturday': 'Shanba',
}

@login_required
def teacher_schedule_view(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    groups = teacher.teachers_groups.all()
    jadval_data = []

    for group in groups:
        group_row = {
            'id': group.id,
            'name': group.name,
            'schedule_list': []
        }

        for day in DAYS_ORDER:
            darslar = Schedule.objects.filter(
                group=group,
                teacher=teacher,  # ❗ Faqat shu o'qituvchiga tegishli darslar
                day=day
            ).order_by('start_time')

            vaqtlar = [
                f"{dars.start_time.strftime('%H:%M')} - {dars.end_time.strftime('%H:%M')}"
                for dars in darslar
            ]

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


@login_required
def create_quiz(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

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

@login_required
def add_questions(request, group_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        time_limit = request.POST.get('time_limit')
        max_score = request.POST.get('max_score')
        total_questions = int(request.POST.get('total_questions', 0))

        if not title:
            return redirect('add_questions', group_id=group.id)

        has_valid_question = False  # Kamida bitta savol borligini tekshiramiz

        quiz = Quiz.objects.create(
            title=title,
            group=group,
            teacher=teacher,
            time_limit=time_limit,
            max_score = max_score
        )

        for i in range(1, total_questions + 1):
            question_text = request.POST.get(f'question_{i}', '').strip()
            if not question_text:
                continue  # Savol matni yo‘q bo‘lsa, bu savolni o‘tkazamiz

            # Variantlarni yig‘amiz
            answers = []
            correct_answer = request.POST.get(f'question_{i}_correct', '')
            for j in range(1, 21):  # Maksimum 20 variantgacha qo‘llab-quvvatlaymiz
                ans_key = f'question_{i}_answer_{j}'
                answer_text = request.POST.get(ans_key, '').strip()
                if answer_text:
                    answers.append((answer_text, str(j) == correct_answer))

            if len(answers) < 2:
                continue  # Kamida 2 ta variant kerak

            if not any(is_correct for _, is_correct in answers):
                continue  # Kamida bitta to‘g‘ri javob bo‘lishi kerak

            # Savolni yaratamiz
            question = Question.objects.create(quiz=quiz, text=question_text)
            for text, is_correct in answers:
                Answer.objects.create(
                    question=question,
                    text=text,
                    is_correct=is_correct
                )

            has_valid_question = True

        if not has_valid_question:
            quiz.delete()
            return redirect('add_questions', group_id=group.id)
        messages.success(request, "Test muvaffaqiyatli qo‘shildi!", extra_tags='test_modal')
        return redirect('create_quiz')

    return render(request, 'teacher-test-group.html', {
        'group': group,
        'teacher': teacher,
    })

@login_required
def quiz_detail(request, quiz_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    quiz = get_object_or_404(Quiz, id=quiz_id, teacher=teacher)
    questions = quiz.questions.prefetch_related('answers')

    if request.method == 'POST':
        # Quiz nomi va vaqtini yangilash
        quiz.title = request.POST.get('title', quiz.title)
        quiz.time_limit = int(request.POST.get('time_limit', quiz.time_limit))
        quiz.max_score = int(request.POST.get('max_score', quiz.max_score))
        quiz.save()

        for question in questions:
            q_text = request.POST.get(f'question_{question.id}')
            if q_text:
                question.text = q_text
                question.save()

            correct_answer_id = request.POST.get(f'correct_{question.id}')

            for answer in question.answers.all():
                a_text = request.POST.get(f'answer_{answer.id}')
                if a_text:
                    answer.text = a_text
                answer.is_correct = str(answer.id) == correct_answer_id
                answer.save()

        messages.success(request, "Test muvaffaqiyatli yangilandi.", extra_tags='test_modal')
        return redirect('create_quiz')

    return render(request, 'quiz_detail.html', {
        'quiz': quiz,
        'questions': questions,
        'teacher': teacher,
    })

@login_required
def teacher_view_results(request, quiz_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

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



@login_required
def teacher_deadline(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    groups = teacher.teachers_groups.all()
    assignments = Assignment.objects.filter(teacher=teacher).select_related('group')

    if request.method == 'POST':
        title = request.POST.get('title')
        group_id = request.POST.get('group_id')
        deadline_str = request.POST.get('deadline')
        file = request.FILES.get('file')
        max_score = request.POST.get('max_score')

        # Barcha maydonlar to‘ldirilganini tekshirish
        if title and group_id and deadline_str and file and max_score:
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

            group = get_object_or_404(Group, id=group_id)
            Assignment.objects.create(
                title=title,
                teacher=teacher,
                group=group,
                deadline=deadline,
                file=file,
                max_score=max_score
            )
            messages.success(request, "Topshiriq muvaffaqiyatli qo‘shildi!", extra_tags='topshir_modal')
            return redirect('teacher_deadline')

    return render(request, 'teacher-upload-deadline.html', {
        'teacher': teacher,
        'groups': groups,
        'assignments': assignments
    })


@login_required
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

    if new_deadline and str(assignment.deadline.strftime('%Y-%m-%dT%H:%M')) != new_deadline:
        assignment.deadline = new_deadline

    if new_group_id and str(assignment.group.id) != str(new_group_id):
        try:
            new_group = Group.objects.get(id=new_group_id)
            assignment.group = new_group
        except Group.DoesNotExist:
            return HttpResponseBadRequest("Guruh topilmadi.")

    if new_file:
        assignment.file = new_file

    # Saqlash
    assignment.save()
    messages.success(request, "Topshiriq muvaffaqiyatli yangilandi!", extra_tags='topshir_modal')
    return redirect('teacher_deadline')

@login_required
def teacher_attendance_groups(request):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')  # faqat o‘qituvchi kiradi

    # Faqat o‘ziga tegishli guruhlarni oladi
    groups = teacher.teachers_groups.all()

    return render(request, 'teacher_attendance_groups.html', {
        'teacher': teacher,
        'groups': groups
    })


@login_required
def submit_attendance(request, group_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    group = get_object_or_404(Group, id=group_id, teachers=teacher)
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    # Bugungi kun nomi: 'monday', 'tuesday', ...
    today_day = timezone.localtime().strftime('%A').lower()

    # Jadvaldan hozirgi dars vaqtini tekshiramiz
    schedule = Schedule.objects.filter(group=group, day=today_day).first()
    if not schedule:
        messages.error(request, "Bugun bu guruhda dars yo‘q!")
        return redirect('teacher_attendance_groups')

    if not (schedule.start_time <= now_time <= schedule.end_time):
        messages.error(request, "Faqat dars vaqtida davomat topshirish mumkin!")
        return redirect('teacher_attendance_groups')

    # Bu dars uchun o‘qituvchi allaqachon davomat topshirganmi?
    already_submitted = Attendance.objects.filter(
        teacher=teacher, group=group, date=today
    ).exists()

    if already_submitted:
        messages.error(request, "Siz bu dars uchun davomat topshirgansiz!")
        return redirect('teacher_attendance_groups')

    # POST bilan kelgan davomat ma'lumotlarini saqlaymiz
    if request.method == 'POST':
        for student in group.students.all():
            status = request.POST.get(f'status_{student.id}')
            Attendance.objects.create(
                student=student,
                teacher=teacher,
                group=group,
                date=today,
                status=status
            )
        return redirect('teacher_attendance_groups')  # yoki o'zingiz xohlagan sahifa

    return render(request, 'teacher_submit_attendance.html', {
        'group': group,
        'students': group.students.all(),
        'schedule': schedule,
        'teacher': teacher,
    })

@login_required
def teacher_group_attendance(request, group_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

    # Faqat o‘ziga biriktirilgan guruh bo‘lishi shart
    group = get_object_or_404(Group, id=group_id, teachers=teacher)

    students = group.students.all()
    attendances = Attendance.objects.filter(group=group).order_by('date')

    # Unikal sanalarni olish
    dates = sorted(set(attendances.values_list('date', flat=True)))

    # Har bir o‘quvchi uchun sana va statusni tayyorlash
    attendance_map = {}
    for student in students:
        student_attendance = {date: None for date in dates}
        records = attendances.filter(student=student)
        for record in records:
            student_attendance[record.date] = record.status
        attendance_map[student.id] = student_attendance

    return render(request, 'teacher_attendance_table.html', {
        'group': group,
        'students': students,
        'dates': dates,
        'attendance_map': attendance_map,
        'teacher': teacher,
    })


@login_required
def teacher_assignment_submissions(request, assignment_id):
    teacher = request.user
    if teacher.role != 'teacher':
        return redirect('login')

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

@login_required
def grade_assignment(request):
    user = request.user
    if user.role != 'teacher':
        return redirect('login')

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

        if score < 0:
            messages.error(request, "Ball manfiy bo‘lishi mumkin emas.")
        elif score > assignment.max_score:
            messages.error(request, f"Ball maksimal {assignment.max_score} dan oshmasligi kerak.")
        else:
            submission.grade = score
            submission.save()
            messages.success(request, "Baholash saqlandi.")

        return redirect('teacher_assignment_submissions', assignment_id=assignment_id)

    else:
        return HttpResponseBadRequest("Faqat POST so‘rovlari qabul qilinadi.")