from datetime import timedelta
from django.utils.timezone import now
from django.core.cache import cache
from main.models import Assignment, AssignmentSubmission, Quiz, StudentQuizResult, SiteSetting, ProfileSetting, SystemAnnouncement, GroupStudentMembership


def all_student_notifications(request):
    user = request.user
    if not user.is_authenticated or getattr(user, 'role', None) != 'student':
        return {}

    today = now()
    upcoming = today + timedelta(days=3)

    # Get student groups and memberships in a single optimized query
    memberships = GroupStudentMembership.objects.filter(student=user).values('group_id', 'group__name', 'joined_at')
    if not memberships:
        return {
            'student_notification_list': [],
            'student_notification_count': 0,
            'quiz_notification_list': [],
            'quiz_notification_count': 0,
            'total_notification_count': 0
        }

    group_ids = [m['group_id'] for m in memberships]
    group_name_map = {m['group_id']: m['group__name'] for m in memberships}
    joined_at_map = {m['group_id']: m['joined_at'] for m in memberships}

    # Topshiriqlar
    assignments = Assignment.objects.filter(
        group_id__in=group_ids,
        deadline__range=(today, upcoming)
    ).select_related('group')

    submitted_ids = set(AssignmentSubmission.objects.filter(student=user, assignment__in=assignments).values_list('assignment_id', flat=True))

    assignment_notifications = []
    for assignment in assignments:
        group_joined = joined_at_map.get(assignment.group_id)
        if group_joined and group_joined <= assignment.created_at and assignment.id not in submitted_ids:
            delta = assignment.deadline - today
            days_left = delta.days
            hours_left = delta.seconds // 3600
            assignment_notifications.append({
                'group': assignment.group.name,
                'title': assignment.title,
                'remaining': f"{days_left} kun, {hours_left} soat"
            })

    # Testlar
    quizzes = Quiz.objects.filter(group_id__in=group_ids).select_related('group')
    done_quiz_ids = set(StudentQuizResult.objects.filter(student=user, quiz__in=quizzes).values_list('quiz_id', flat=True))

    quiz_notifications = []
    for quiz in quizzes:
        group_joined = joined_at_map.get(quiz.group_id)
        if group_joined and group_joined <= quiz.created_at and quiz.id not in done_quiz_ids:
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
    if not user.is_authenticated or getattr(user, 'role', None) != 'teacher':
        return {}

    today = now()
    three_days_ago = today - timedelta(days=3)

    # Optimize query using SQL aggregation (inner join & filter on grade IS NULL) to do everything in the DB in a single query
    expired_assignments = Assignment.objects.filter(
        teacher=user,
        deadline__lt=today,
        deadline__gte=three_days_ago,
        submissions__grade__isnull=True
    ).select_related('group').distinct()

    notification_list = [
        {
            'title': assignment.title,
            'group': assignment.group.name,
            'message': 'Topshiriqni baholang, muddati tugadi'
        }
        for assignment in expired_assignments
    ]

    return {
        'teacher_notifications': notification_list,
        'teacher_notif_count': len(notification_list),
    }


def site_images(request):
    # Cache global site settings for 300 seconds to prevent DB hits on every single page load
    cached_data = cache.get('site_global_images')
    if cached_data is not None:
        return cached_data

    setting = SiteSetting.objects.first()
    profile = ProfileSetting.objects.first()

    data = {
        'site_name': setting.site_name if setting and setting.site_name else "Tizim",
        'global_image': setting.image.url if setting and setting.image else None,
        'default_profile_image': profile.image.url if profile and profile.image else None
    }
    cache.set('site_global_images', data, 300)
    return data


def system_announcements(request):
    if not request.user.is_authenticated:
        return {}

    current_now = now()
    role = getattr(request.user, 'role', 'admin')

    # Get active announcements with cached role list for 60 seconds
    cache_key = f'active_announcements_{role}'
    announcements = cache.get(cache_key)
    if announcements is None:
        announcements = list(SystemAnnouncement.objects.filter(
            is_active=True,
            start_time__lte=current_now,
            end_time__gte=current_now,
            target_role__in=['all', role]
        ).order_by('-created_at'))
        cache.set(cache_key, announcements, 60)

    always_show = []
    one_time = []

    if 'seen_announcements' not in request.session:
        request.session['seen_announcements'] = []

    seen_ids = request.session['seen_announcements']
    if not isinstance(seen_ids, list):
        seen_ids = list(seen_ids)
        request.session['seen_announcements'] = seen_ids

    for announce in announcements:
        if announce.category == 'always_show':
            always_show.append(announce)
        elif announce.category == 'one_time':
            if announce.id not in seen_ids:
                one_time.append(announce)

    return {
        'always_show_announcements': always_show,
        'one_time_announcements': one_time,
    }


def error_notifications(request):
    user = request.user
    if user and user.is_authenticated and (user.role == 'admin' or user.is_superuser or user.is_staff):
        from main.models import SystemErrorLog
        unread_errors = SystemErrorLog.objects.filter(is_resolved=False).count()
        return {
            'unread_errors_count': unread_errors
        }
    return {
        'unread_errors_count': 0
    }