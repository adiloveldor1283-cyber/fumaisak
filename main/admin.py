from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.safestring import mark_safe
from django.utils.timezone import localtime
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    CustomUser, Subject, SubjectMaterial, Group, GroupStudentMembership, Schedule,
    Quiz, Question, Answer, StudentQuizResult, StudentAnswer,
    Assignment, AssignmentSubmission, Attendance,
    SiteSetting, TelegramBotContact, ProfileSetting,
    GroupPaymentInfo, StudentPayment,
    AIQuiz, AIQuestion, AIAnswer, StudentAIAnswer, StudentAIPlan,
    SystemAnnouncement, GroupLesson, AuditLog, UserSession, GroupVideo,
    DTMQuestionPool, DTMAnswerPool, DTMExam, DTMRegistration, StudentDTMExamResult,
    SystemErrorLog, LockedPage, MonitoringAPIKey, Book, TeacherSalaryPayment,
    WalletTransaction, PaymentOrder, PaymeTransaction, ClickTransaction
)


# ==============================================================================
# 1. FOYDALANUVCHILAR VA GURUHLAR
# ==============================================================================

class StudentGroupMembershipInline(TabularInline):
    model = GroupStudentMembership
    fk_name = 'student'
    extra = 1


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ModelAdmin):
    model = CustomUser
    inlines = [StudentGroupMembershipInline]
    list_display = ['username', 'last_name', 'first_name', 'middle_name', 'role', 'phone_number', 'balance', 'is_archived', 'group_count', 'related_teachers_count', 'active_sessions_count']
    list_filter = ['role', 'is_archived', 'is_active', 'is_profile_completed']
    search_fields = ['first_name', 'last_name', 'middle_name', 'username', 'phone_number']
    readonly_fields = UserAdmin.readonly_fields + ('group_details', 'archived_at')

    fieldsets = UserAdmin.fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('middle_name', 'role', 'phone_number', 'profile_image', 'balance', 'is_archived', 'archived_at', 'subadmin_permissions', 'group_details')}),
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
        count = getattr(obj, 'active_sessions_cnt', 0)
        return format_html('<strong style="color: {};">{} ta faol</strong>', '#00ffaa' if count > 0 else 'rgba(255,255,255,0.4)', count)
    active_sessions_count.short_description = "Faol seanslar"

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('role', 'profile_image', 'balance')}),
    )

    def group_count(self, obj):
        if obj.role == 'teacher':
            return obj.teachers_groups.count()
        elif obj.role == 'student':
            return obj.student_groups.count()
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
    extra = 1


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    list_display = ['name', 'subject', 'salary_type', 'salary_rate', 'is_active', 'students_count', 'formatted_created_at']
    list_filter = ['is_active', 'subject', 'salary_type']
    fields = ('name', 'subject', 'teachers', 'is_active', 'closed_at', 'salary_type', 'salary_rate', 'created_at')
    filter_horizontal = ('teachers',)
    search_fields = [
        'name',
        'students__first_name', 'students__last_name',
        'teachers__first_name', 'teachers__last_name'
    ]
    inlines = [GroupStudentMembershipInline]

    def formatted_created_at(self, obj):
        return localtime(obj.created_at).strftime('%d.%m.%Y %H:%M')
    formatted_created_at.short_description = 'Yaratilgan vaqti'

    def students_count(self, obj):
        return obj.students.count()
    students_count.short_description = "O'quvchilar soni"


@admin.register(GroupStudentMembership)
class GroupStudentMembershipAdmin(ModelAdmin):
    list_display = ['student', 'group', 'joined_at']
    list_filter = ['group', 'joined_at']
    search_fields = ['student__first_name', 'student__last_name', 'group__name']


@admin.register(Schedule)
class ScheduleAdmin(ModelAdmin):
    list_display = ('group', 'teacher', 'get_day_display', 'start_time', 'end_time')
    list_filter = ('group', 'teacher', 'day')
    search_fields = ('group__name', 'teacher__first_name', 'teacher__last_name')


@admin.register(Attendance)
class AttendanceAdmin(ModelAdmin):
    list_display = ('student_name', 'teacher_name', 'group', 'date', 'status', 'created_at')
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


@admin.register(TelegramBotContact)
class TelegramBotContactAdmin(ModelAdmin):
    list_display = ('phone_clean', 'chat_id', 'first_name', 'last_name', 'username', 'updated_at')
    search_fields = ('phone_clean', 'chat_id', 'first_name', 'last_name', 'username')


@admin.register(UserSession)
class UserSessionAdmin(ModelAdmin):
    list_display = ('user', 'user_role', 'ip_address', 'location', 'device_type', 'browser', 'os', 'last_activity', 'is_active')
    list_filter = ('user__role', 'is_active', 'device_type', 'browser', 'os')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ip_address', 'location')
    readonly_fields = ('session_key', 'user', 'ip_address', 'location', 'user_agent', 'device_type', 'browser', 'os', 'created_at', 'last_activity')

    def user_role(self, obj):
        if not obj.user:
            return '-'
        if obj.user.is_superuser or obj.user.role == 'admin':
            return format_html('<span style="color: #ff0055; font-weight: bold;">ADMIN</span>')
        elif obj.user.role == 'reception':
            return format_html('<span style="color: #f59e0b; font-weight: bold;">SUB-ADMIN</span>')
        elif obj.user.role == 'teacher':
            return format_html('<span style="color: #9b51e0; font-weight: bold;">O‘QITUVCHI</span>')
        return format_html('<span style="color: #00f2fe; font-weight: bold;">O‘QUVCHI</span>')
    user_role.short_description = "Roli"

    def has_add_permission(self, request):
        return False


# ==============================================================================
# 2. FANLAR, DARSLAR VA O'QUV MATERIALLARI
# ==============================================================================

class SubjectMaterialInline(TabularInline):
    model = SubjectMaterial
    extra = 1


@admin.register(Subject)
class SubjectAdmin(ModelAdmin):
    list_display = ('name', 'description', 'materials_count', 'books_count', 'created_at')
    search_fields = ('name', 'description')
    inlines = [SubjectMaterialInline]

    def materials_count(self, obj):
        return obj.materials.count()
    materials_count.short_description = "Materiallar soni"

    def books_count(self, obj):
        return obj.books.count()
    books_count.short_description = "Kitoblar soni"


@admin.register(SubjectMaterial)
class SubjectMaterialAdmin(ModelAdmin):
    list_display = ('title', 'subject', 'uploaded_by', 'created_at')
    list_filter = ('subject', 'uploaded_by')
    search_fields = ('title', 'description', 'subject__name')


@admin.register(GroupLesson)
class GroupLessonAdmin(ModelAdmin):
    list_display = ('group', 'date', 'topic', 'created_at')
    list_filter = ('group', 'date')
    search_fields = ('topic', 'notes', 'homework', 'group__name')


@admin.register(Book)
class BookAdmin(ModelAdmin):
    list_display = ('title', 'subject', 'uploaded_by', 'created_at')
    list_filter = ('subject', 'uploaded_by')
    search_fields = ('title', 'subject__name', 'uploaded_by__first_name', 'uploaded_by__last_name')


@admin.register(GroupVideo)
class GroupVideoAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'created_at')
    list_filter = ('group', 'teacher')
    search_fields = ('title', 'group__name')


class AssignmentSubmissionInline(TabularInline):
    model = AssignmentSubmission
    extra = 0
    readonly_fields = ('submitted_at',)


@admin.register(Assignment)
class AssignmentAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'max_score', 'formatted_deadline', 'created_at')
    list_filter = ('group', 'teacher')
    search_fields = ('title', 'group__name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')
    ordering = ('-created_at',)
    date_hierarchy = 'deadline'
    list_per_page = 25
    inlines = [AssignmentSubmissionInline]

    def formatted_deadline(self, obj):
        return obj.deadline.strftime('%d.%m.%Y %H:%M')
    formatted_deadline.short_description = 'Muddati'


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(ModelAdmin):
    list_display = ('assignment', 'student', 'grade', 'submitted_at')
    list_filter = ('assignment__group', 'grade', 'submitted_at')
    search_fields = ('student__first_name', 'student__last_name', 'assignment__title')


# ==============================================================================
# 3. MOLIYA, TO'LOVLAR VA HAMYON
# ==============================================================================

@admin.register(GroupPaymentInfo)
class GroupPaymentInfoAdmin(ModelAdmin):
    list_display = ('group', 'course_duration_months', 'monthly_fee', 'start_date', 'created_at', 'updated_at')
    search_fields = ('group__name',)
    list_filter = ('created_at',)


@admin.register(StudentPayment)
class StudentPaymentAdmin(ModelAdmin):
    list_display = ("student", "group", "month", "cycle_number", "amount_paid", "paid_at")
    list_filter = ("group", "month", "cycle_number")
    search_fields = ("student__first_name", "student__last_name", "group__name")


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


@admin.register(PaymentOrder)
class PaymentOrderAdmin(ModelAdmin):
    list_display = ('student', 'group', 'month', 'amount', 'provider', 'status', 'transaction_id', 'created_at', 'paid_at')
    list_filter = ('provider', 'status', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'group__name', 'transaction_id')


@admin.register(PaymeTransaction)
class PaymeTransactionAdmin(ModelAdmin):
    list_display = ('order', 'transaction_id', 'amount', 'state', 'reason', 'created_at', 'performed_at')
    list_filter = ('state', 'created_at')
    search_fields = ('transaction_id', 'order__student__first_name', 'order__student__last_name')


@admin.register(ClickTransaction)
class ClickTransactionAdmin(ModelAdmin):
    list_display = ('order', 'click_trans_id', 'amount', 'action', 'status', 'created_at')
    list_filter = ('status', 'action', 'created_at')
    search_fields = ('click_trans_id', 'order__student__first_name', 'order__student__last_name')


# ==============================================================================
# 4. GURUH TESTLARI VA DTM IMTIHONLARI
# ==============================================================================

class AnswerInline(TabularInline):
    model = Answer
    extra = 2


class QuestionInline(TabularInline):
    model = Question
    extra = 1


@admin.register(Quiz)
class QuizAdmin(ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'time_limit', 'max_score', 'created_at')
    list_filter = ('group', 'teacher', 'created_at')
    search_fields = ('title', 'group__name')
    ordering = ('-created_at',)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    list_display = ('text', 'quiz')
    search_fields = ('text', 'quiz__title')
    list_filter = ('quiz',)
    inlines = [AnswerInline]


@admin.register(Answer)
class AnswerAdmin(ModelAdmin):
    list_display = ('text', 'question', 'is_correct')
    list_filter = ('is_correct', 'question__quiz')
    search_fields = ('text', 'question__text')


class StudentAnswerInline(TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ('question', 'selected_answer')


@admin.register(StudentQuizResult)
class StudentQuizResultAdmin(ModelAdmin):
    list_display = ('student', 'quiz', 'score', 'submitted_at')
    list_filter = ('quiz', 'submitted_at')
    search_fields = ('student__first_name', 'student__last_name', 'quiz__title')
    inlines = [StudentAnswerInline]


@admin.register(StudentAnswer)
class StudentAnswerAdmin(ModelAdmin):
    list_display = ('result', 'question', 'selected_answer')
    list_filter = ('result__quiz',)
    search_fields = ('result__student__first_name', 'result__student__last_name', 'question__text')


class DTMAnswerPoolInline(TabularInline):
    model = DTMAnswerPool
    extra = 3


@admin.register(DTMQuestionPool)
class DTMQuestionPoolAdmin(ModelAdmin):
    list_display = ('subject', 'difficulty', 'is_compulsory', 'short_text')
    list_filter = ('subject', 'difficulty', 'is_compulsory')
    search_fields = ('text', 'subject__name')
    inlines = [DTMAnswerPoolInline]

    def short_text(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    short_text.short_description = "Savol matni"


@admin.register(DTMAnswerPool)
class DTMAnswerPoolAdmin(ModelAdmin):
    list_display = ('question', 'text', 'is_correct')
    list_filter = ('is_correct', 'question__subject')
    search_fields = ('text', 'question__text')


@admin.register(DTMExam)
class DTMExamAdmin(ModelAdmin):
    list_display = ('title', 'registration_deadline', 'exam_date', 'is_active', 'registrations_count')
    list_filter = ('is_active', 'exam_date')
    search_fields = ('title',)

    def registrations_count(self, obj):
        return obj.registrations.count()
    registrations_count.short_description = "Ro'yxatdan o'tganlar soni"


@admin.register(DTMRegistration)
class DTMRegistrationAdmin(ModelAdmin):
    list_display = ('student', 'exam', 'block1_subject', 'block2_subject', 'take_compulsory', 'booklet_number', 'registered_at')
    list_filter = ('exam', 'block1_subject', 'block2_subject', 'take_compulsory')
    search_fields = ('student__first_name', 'student__last_name', 'booklet_number', 'exam__title')


@admin.register(StudentDTMExamResult)
class StudentDTMExamResultAdmin(ModelAdmin):
    list_display = ('registration', 'total_score', 'score_block1', 'score_block2', 'score_compulsory', 'processed_at')
    list_filter = ('registration__exam', 'processed_at')
    search_fields = ('registration__student__first_name', 'registration__student__last_name', 'registration__exam__title')


# ==============================================================================
# 5. AI TESTLAR VA O'QUV REJALARI
# ==============================================================================

class AIAnswerInline(TabularInline):
    model = AIAnswer
    extra = 3


class AIQuestionInline(TabularInline):
    model = AIQuestion
    extra = 1


@admin.register(AIQuiz)
class AIQuizAdmin(ModelAdmin):
    list_display = ('student', 'title', 'level', 'score', 'max_score', 'is_completed', 'created_at')
    list_filter = ('level', 'is_completed', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'title')
    inlines = [AIQuestionInline]


@admin.register(AIQuestion)
class AIQuestionAdmin(ModelAdmin):
    list_display = ('quiz', 'text', 'correct_explanation')
    list_filter = ('quiz__level',)
    search_fields = ('text', 'quiz__title')
    inlines = [AIAnswerInline]


@admin.register(AIAnswer)
class AIAnswerAdmin(ModelAdmin):
    list_display = ('question', 'text', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('text', 'question__text')


@admin.register(StudentAIAnswer)
class StudentAIAnswerAdmin(ModelAdmin):
    list_display = ('quiz', 'question', 'selected_answer')
    search_fields = ('quiz__student__first_name', 'question__text')


@admin.register(StudentAIPlan)
class StudentAIPlanAdmin(ModelAdmin):
    list_display = ('student', 'updated_at')
    search_fields = ('student__first_name', 'student__last_name', 'student__username')


# ==============================================================================
# 6. TIZIM, XAVFSIZLIK VA SOZLAMALAR
# ==============================================================================

@admin.register(SiteSetting)
class SiteSettingAdmin(ModelAdmin):
    list_display = ('site_name', 'sms_enabled', 'telegram_enabled', 'eskiz_from_name', 'telegram_bot_username')

    def has_add_permission(self, request):
        if SiteSetting.objects.exists():
            return False
        return True


@admin.register(ProfileSetting)
class ProfileSettingAdmin(ModelAdmin):
    list_display = ('id', 'image')

    def has_add_permission(self, request):
        if ProfileSetting.objects.exists():
            return False
        return True


@admin.register(SystemAnnouncement)
class SystemAnnouncementAdmin(ModelAdmin):
    list_display = ('title', 'target_role', 'category', 'is_active', 'start_time', 'end_time', 'created_at')
    list_filter = ('target_role', 'category', 'is_active')
    search_fields = ('title', 'message')


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'action', 'description', 'ip_address')
    readonly_fields = ('user', 'action', 'description', 'timestamp', 'ip_address')

    def has_add_permission(self, request):
        return False


@admin.register(SystemErrorLog)
class SystemErrorLogAdmin(ModelAdmin):
    list_display = ('user', 'url_path', 'http_method', 'exception_type', 'error_message', 'is_resolved', 'timestamp')
    list_filter = ('is_resolved', 'http_method', 'exception_type', 'timestamp')
    search_fields = ('user__username', 'url_path', 'error_message', 'exception_type', 'ip_address')
    readonly_fields = ('user', 'user_role', 'user_phone', 'url_path', 'http_method', 'exception_type', 'error_message', 'traceback', 'ip_address', 'user_agent', 'request_data', 'timestamp')


@admin.register(LockedPage)
class LockedPageAdmin(ModelAdmin):
    list_display = ('url_path', 'reason', 'is_active', 'locked_at')
    list_filter = ('is_active', 'locked_at')
    search_fields = ('url_path', 'reason')


@admin.register(MonitoringAPIKey)
class MonitoringAPIKeyAdmin(ModelAdmin):
    list_display = ('name', 'key', 'is_active', 'created_by', 'created_at', 'last_used_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'key')