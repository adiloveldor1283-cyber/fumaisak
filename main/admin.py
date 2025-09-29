from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe



from .models import CustomUser, Group, Schedule, DAYS_OF_WEEK, Answer, Question, Quiz, Attendance, Assignment, \
    StudentQuizResult, StudentAnswer, AssignmentSubmission, GroupStudentMembership, SiteSetting, ProfileSetting, \
    GroupPaymentInfo, StudentPayment
from django.utils.timezone import localtime

class StudentGroupMembershipInline(admin.TabularInline):
    model = GroupStudentMembership
    fk_name = 'student'  # bu muhim
    extra = 1


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    inlines = [StudentGroupMembershipInline]
    list_display = ['username', 'first_name', 'last_name', 'role', 'group_count', 'related_teachers_count']
    list_filter = ['role']
    search_fields = ['first_name', 'last_name', 'username']
    readonly_fields = UserAdmin.readonly_fields + ('group_details',)

    fieldsets = UserAdmin.fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('role', 'profile_image', 'group_details')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Qo‘shimcha Ma’lumotlar', {'fields': ('role', 'profile_image')}),
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
                details += f"<strong>{group.name}</strong><br>"
                for student in group.students.all():
                    details += f"— {student.first_name} {student.last_name}<br>"
                details += "<br>"
            return mark_safe(details if details else "Hech qanday guruh yo'q.")

        elif obj.role == 'student':
            details = ""
            for group in obj.student_groups.all():
                details += f"<strong>{group.name}</strong><br>"
                for teacher in group.teachers.all():
                    details += f"— {teacher.first_name} {teacher.last_name}<br>"
                details += "<br>"
            return mark_safe(details if details else "Hech qanday guruh yo'q.")

        return "Noma'lum rol"

    group_details.short_description = "Guruh tafsilotlari"

class GroupStudentMembershipInline(admin.TabularInline):
    model = GroupStudentMembership
    extra = 1  # Qo‘shimcha qatordan boshlansin


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'formatted_created_at']
    fields = ('name', 'teachers', 'created_at')
    filter_horizontal = ('teachers',)
    search_fields = [
        'students__first_name', 'students__last_name',
        'teachers__first_name', 'teachers__last_name'
    ]
    inlines = [GroupStudentMembershipInline]

    def formatted_created_at(self, obj):
        return localtime(obj.created_at).strftime('%Y-%m-%d %H:%M')
    formatted_created_at.short_description = 'Yaratilgan vaqti'




@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('group', 'get_day_display', 'start_time', 'end_time')
    list_filter = ('group', 'day')
    search_fields = ('group__name',)

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 2


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'created_at')
    list_filter = ('group', 'teacher', 'created_at')
    search_fields = ('title',)
    ordering = ('-created_at',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'quiz')
    search_fields = ('text',)
    list_filter = ('quiz',)
    inlines = [AnswerInline]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('text', 'question', 'is_correct')
    list_filter = ('is_correct', 'question')
    search_fields = ('text',)


# Qolgan modellarning oddiy ro‘yxatga olish (istalgancha sozlash mumkin)
admin.site.register(StudentQuizResult)
admin.site.register(StudentAnswer)
admin.site.register(AssignmentSubmission)

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
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
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'teacher', 'formatted_deadline', 'created_at')
    list_filter = ('group', 'teacher')
    search_fields = ('title', 'group__name', 'teacher__username')
    ordering = ('-created_at',)
    date_hierarchy = 'deadline'
    list_per_page = 25

    def formatted_deadline(self, obj):
        return obj.deadline.strftime('%Y-%m-%d %H:%M')
    formatted_deadline.short_description = 'Muddati'


@admin.register(GroupStudentMembership)
class GroupStudentMembershipAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'joined_at']
    list_filter = ['group', 'joined_at']
    search_fields = ['student__first_name', 'student__last_name', 'group__name']



@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Faqat 1 ta obyekt yaratilishiga ruxsat
        if SiteSetting.objects.exists():
            return False
        return True


@admin.register(ProfileSetting)
class ProfileSettingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Faqat 1 ta obyekt yaratilishiga ruxsat
        if ProfileSetting.objects.exists():
            return False
        return True

@admin.register(GroupPaymentInfo)
class GroupPaymentInfoAdmin(admin.ModelAdmin):
    list_display = ('group', 'course_duration_months', 'monthly_fee', 'total_fee', 'created_at', 'updated_at')
    search_fields = ('group__name',)
    list_filter = ('created_at',)

@admin.register(StudentPayment)
class StudentPaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "group", "month", "amount_paid", "paid_at")
    list_filter = ("group", "month")
    search_fields = ("student__first_name", "student__last_name", "group__name")