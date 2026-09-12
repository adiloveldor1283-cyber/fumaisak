from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline

from .models import CustomUser, Group, Schedule, DAYS_OF_WEEK, Answer, Question, Quiz, Attendance, Assignment, \
    StudentQuizResult, StudentAnswer, AssignmentSubmission, GroupStudentMembership, SiteSetting, ProfileSetting, \
    GroupPaymentInfo, StudentPayment, UserSession, GroupVideo, Subject, Book, TeacherSalaryPayment, WalletTransaction
from django.utils.timezone import localtime

class StudentGroupMembershipInline(TabularInline):
    model = GroupStudentMembership
    fk_name = 'student'  # bu muhim
    extra = 1


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ModelAdmin):
    model = CustomUser
    inlines = [StudentGroupMembershipInline]
    list_display = ['username', 'last_name', 'first_name', 'middle_name', 'role', 'phone_number', 'balance', 'group_count', 'related_teachers_count', 'active_sessions_count']
    list_filter = ['role']
    search_fields = ['first_name', 'last_name', 'middle_name', 'username', 'phone_number']
    readonly_fields = UserAdmin.readonly_fields + ('group_details',)

    fieldsets = UserAdmin.fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('middle_name', 'role', 'phone_number', 'profile_image', 'balance', 'group_details')}),
    )

    def get_queryset(self, request):
        from django.db.models import Count, Q
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            'student_groups__teachers',
            'teachers_groups'
        ).annotate(
            active_sessions_cnt=Count('sessions', filter=Q(sessions__is_active=True))
        )

    def active_sessions_count(self, obj):
        count = obj.active_sessions_cnt
        return format_html('<strong style="color: {};">{} ta faol</strong>', '#00ffaa' if count > 0 else 'rgba(255,255,255,0.4)', count)
    active_sessions_count.short_description = "Faol seanslar"
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('role', 'profile_image', 'balance')}),
    )

    def group_count(self, obj):
        if obj.role == 'teacher':
            return len(obj.teachers_groups.all())
        elif obj.role == 'student':
            return len(obj.student_groups.all())
        return '-'

    group_count.short_description = "Guruhlar soni"

    def related_teachers_count(self, obj):
        if obj.role == 'student':
            teachers = set()
            for group in obj.student_groups.all():
                teachers.update(group.teachers.all())
            return len(teachers)
        return '-'


    related_teachers_count.short_description = "O‘qituvchilar soni"

    def group_details(self, obj):
        if obj.role == 'teacher':
            details = ""
            for group in obj.teachers_groups.all():
                details += f"<strong>{escape(group.name)}</strong><br>"
                for student in group.students.all():
                    details += f"— {escape(student.first_name)} {escape(student.last_name)}<br>"
                details += "<br>"
            return mark_safe(details if details else "Hech qanday guruh yo'q.")

        elif obj.role == 'student':
            details = ""
            for group in obj.student_groups.all():
                details += f"<strong>{escape(group.name)}</strong><br>"
                for teacher in group.teachers.all():
                    details += f"— {escape(teacher.first_name)} {escape(teacher.last_name)}<br>"
                details += "<br>"
            return mark_safe(details if details else "Hech qanday guruh yo'q.")

        return "Noma'lum rol"

    group_details.short_description = "Guruh tafsilotlari"

class GroupStudentMembershipInline(TabularInline):
    model = GroupStudentMembership
    extra = 1  # Qo‘shimcha qatordan boshlansin


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    list_display = ['name', 'subject', 'salary_type', 'salary_rate', 'formatted_created_at']
    fields = ('name', 'subject', 'teachers', 'salary_type', 'salary_rate', 'created_at')
    filter_horizontal = ('teachers',)
    search_fields = [
        'students__first_name', 'students__last_name',
        'teachers__first_name', 'teachers__last_name'
    ]
    inlines = [GroupStudentMembershipInline]

    def formatted_created_at(self, obj):
        return localtime(obj.created_at).strftime('%d.%m.%Y %H:%M')
    formatted_created_at.short_description = 'Yaratilgan vaqti'


@admin.register(Schedule)
class ScheduleAdmin(ModelAdmin):
    list_display = ('group', 'get_day_display', 'start_time', 'end_time')
    list_filter = ('group', 'day')
    search_fields = ('group__name',)

class AnswerInline(TabularInline):
    model = Answer
    extra = 2


class QuestionInline(TabularInline):
    model = Question
    extra = 1


@admin.register(Quiz)
class QuizAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'created_at')
    list_filter = ('group', 'teacher', 'created_at')
    search_fields = ('title',)
    ordering = ('-created_at',)


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    list_display = ('text', 'quiz')
    search_fields = ('text',)
    list_filter = ('quiz',)
    inlines = [AnswerInline]


@admin.register(Answer)
class AnswerAdmin(ModelAdmin):
    list_display = ('text', 'question', 'is_correct')
    list_filter = ('is_correct', 'question')
    search_fields = ('text',)


@admin.register(StudentQuizResult)
class StudentQuizResultAdmin(ModelAdmin):
    pass

@admin.register(StudentAnswer)
class StudentAnswerAdmin(ModelAdmin):
    pass

@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(ModelAdmin):
    pass


@admin.register(Attendance)
class AttendanceAdmin(ModelAdmin):
    list_display = ('student_name', 'teacher_name', 'group', 'date', 'status')
    list_filter = ('group', 'teacher', 'status', 'date')
    search_fields = ('student__first_name', 'student__last_name',
                     'teacher__first_name', 'teacher__last_name',
                     'group__name')

    def student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
    student_name.short_description = "O‘quvchi"

    def teacher_name(self, obj):
        return f"{obj.teacher.first_name} {obj.teacher.last_name}"
    teacher_name.short_description = "O‘qituvchi"

@admin.register(Assignment)
class AssignmentAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'formatted_deadline', 'created_at')
    list_filter = ('group', 'teacher')
    search_fields = ('title', 'group__name', 'teacher__username')
    ordering = ('-created_at',)
    date_hierarchy = 'deadline'
    list_per_page = 25

    def formatted_deadline(self, obj):
        return obj.deadline.strftime('%d.%m.%Y %H:%M')
    formatted_deadline.short_description = 'Muddati'


@admin.register(GroupStudentMembership)
class GroupStudentMembershipAdmin(ModelAdmin):
    list_display = ['student', 'group', 'joined_at']
    list_filter = ['group', 'joined_at']
    search_fields = ['student__first_name', 'student__last_name', 'group__name']


@admin.register(SiteSetting)
class SiteSettingAdmin(ModelAdmin):
    def has_add_permission(self, request):
        # Faqat 1 ta obyekt yaratilishiga ruxsat
        if SiteSetting.objects.exists():
            return False
        return True


@admin.register(ProfileSetting)
class ProfileSettingAdmin(ModelAdmin):
    def has_add_permission(self, request):
        # Faqat 1 ta obyekt yaratilishiga ruxsat
        if ProfileSetting.objects.exists():
            return False
        return True

@admin.register(GroupPaymentInfo)
class GroupPaymentInfoAdmin(ModelAdmin):
    list_display = ('group', 'course_duration_months', 'monthly_fee', 'total_fee', 'created_at', 'updated_at')
    search_fields = ('group__name',)
    list_filter = ('created_at',)

@admin.register(StudentPayment)
class StudentPaymentAdmin(ModelAdmin):
    list_display = ("student", "group", "month", "amount_paid", "paid_at")
    list_filter = ("group", "month")
    search_fields = ("student__first_name", "student__last_name", "group__name")


@admin.register(UserSession)
class UserSessionAdmin(ModelAdmin):
    list_display = ('user', 'ip_address', 'location', 'device_type', 'browser', 'os', 'last_activity', 'is_active')
    list_filter = ('device_type', 'browser', 'os', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ip_address', 'location')
    readonly_fields = ('session_key', 'user', 'ip_address', 'location', 'user_agent', 'device_type', 'browser', 'os', 'created_at', 'last_activity')

    def has_add_permission(self, request):
        return False


@admin.register(GroupVideo)
class GroupVideoAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'created_at')
    list_filter = ('group', 'teacher')
    search_fields = ('title', 'group__name')


@admin.register(Book)
class BookAdmin(ModelAdmin):
    list_display = ('title', 'subject', 'uploaded_by', 'created_at')
    list_filter = ('subject', 'uploaded_by')
    search_fields = ('title', 'subject__name', 'uploaded_by__first_name', 'uploaded_by__last_name')


@admin.register(TeacherSalaryPayment)
class TeacherSalaryPaymentAdmin(ModelAdmin):
    list_display = ('teacher', 'group', 'amount', 'month', 'paid_at', 'paid_by')
    list_filter = ('month', 'paid_at', 'teacher')
    search_fields = ('teacher__first_name', 'teacher__last_name', 'group__name', 'month')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = ('student', 'amount', 'transaction_type', 'description', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'student__username', 'description')