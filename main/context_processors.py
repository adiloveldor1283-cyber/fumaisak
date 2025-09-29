from datetime import timedelta
from django.utils.timezone import now
from main.models import Assignment, AssignmentSubmission, Quiz, StudentQuizResult, SiteSetting, ProfileSetting
from django.utils import timezone

from django.utils.timezone import now
from datetime import timedelta
from .models import GroupStudentMembership

def all_student_notifications(request):
    user = request.user
    if not user.is_authenticated or user.role != 'student':
        return {}

    today = now()
    upcoming = today + timedelta(days=3)

    groups = user.student_groups.all()

    # Topshiriqlar
    assignments = Assignment.objects.filter(
        group__in=groups,
        deadline__range=(today, upcoming)
    )
    submitted_ids = AssignmentSubmission.objects.filter(student=user).values_list('assignment_id', flat=True)

    assignment_notifications = []
    for assignment in assignments:
        if GroupStudentMembership.objects.filter(
            student=user,
            group=assignment.group,
            joined_at__lte=assignment.created_at
        ).exists() and assignment.id not in submitted_ids:
            delta = assignment.deadline - today
            days_left = delta.days
            hours_left = delta.seconds // 3600
            assignment_notifications.append({
                'group': assignment.group.name,
                'title': assignment.title,
                'remaining': f"{days_left} kun, {hours_left} soat"
            })

    # Testlar
    quizzes = Quiz.objects.filter(group__in=groups)
    done_quiz_ids = StudentQuizResult.objects.filter(student=user).values_list('quiz_id', flat=True)

    quiz_notifications = []
    for quiz in quizzes:
        if GroupStudentMembership.objects.filter(
            student=user,
            group=quiz.group,
            joined_at__lte=quiz.created_at
        ).exists() and quiz.id not in done_quiz_ids:
            quiz_notifications.append(quiz)

    return {
        'student_notification_list': assignment_notifications,
        'student_notification_count': len(assignment_notifications),
        'quiz_notification_list': quiz_notifications,
        'quiz_notification_count': len(quiz_notifications),
        'total_notification_count': len(assignment_notifications) + len(quiz_notifications)
    }



def teacher_notifications(request):
    user = request.user
    if not user.is_authenticated or user.role != 'teacher':
        return {}

    today = timezone.now()
    three_days_ago = today - timedelta(days=3)

    expired_assignments = Assignment.objects.filter(
        teacher=user,
        deadline__lt=today,
        deadline__gte=three_days_ago
    ).order_by('-deadline')

    notification_list = []

    for assignment in expired_assignments:
        # Shu topshiriq bo‘yicha barcha topshiruvlar
        all_submissions = AssignmentSubmission.objects.filter(assignment=assignment)
        if not all_submissions.exists():
            continue  # hech kim topshirmagan → bildirishnoma chiqmasin

        # Baho qo‘yilmaganlar borligini tekshiramiz
        ungraded = all_submissions.filter(grade__isnull=True)
        if ungraded.exists():
            notification_list.append({
                'title': assignment.title,
                'group': assignment.group.name,
                'message': 'Topshiriqni baholang, muddati tugadi'
            })

    return {
        'teacher_notifications': notification_list,
        'teacher_notif_count': len(notification_list),
    }


def site_images(request):
    setting = SiteSetting.objects.first()
    profile = ProfileSetting.objects.first()
    return {
        'global_image': setting.image.url if setting and setting.image else None,
        'default_profile_image': profile.image.url if profile and profile.image else None
    }