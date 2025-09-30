from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def user_profile_image_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{instance.username}_profile.{ext}'
    return f'profiles/{filename}'



class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', "Administrator"),
        ('teacher', "O'qituvchi"),
        ('student', "O'quvchi"),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES)
    profile_image = models.ImageField(upload_to=user_profile_image_path, blank=True, null=True)
    phone_number = models.CharField(max_length=20, verbose_name="Telefon raqami", blank=False)
    joined_at = models.DateTimeField(verbose_name="Qo'shilgan vaqti", default=timezone.now)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"

class Group(models.Model):
    name = models.CharField(max_length=200)
    students = models.ManyToManyField(CustomUser, through='GroupStudentMembership', related_name='student_groups', limit_choices_to={'role': 'student'})
    teachers = models.ManyToManyField(CustomUser, related_name='teachers_groups', limit_choices_to={'role': 'teacher'})
    created_at = models.DateTimeField(verbose_name='Guruh ochilgan vaqti', default=timezone.now)

    def __str__(self):
        return self.name

class GroupStudentMembership(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'group')

    def __str__(self):
        return f"{self.student} -> {self.group} ({self.joined_at})"


DAYS_OF_WEEK = (
    ('monday', 'Dushanba'),
    ('tuesday', 'Seshanba'),
    ('wednesday', 'Chorshanba'),
    ('thursday', 'Payshanba'),
    ('friday', 'Juma'),
    ('saturday', 'Shanba'),
)

class Schedule(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='schedules')
    teacher = models.ForeignKey(CustomUser,
                                on_delete=models.CASCADE,
                                related_name='schedules',
                                limit_choices_to={'role': 'teacher'})
    day = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"{self.group.name} - {self.get_day_display()} ({self.start_time} - {self.end_time})"

class Quiz(models.Model):
    title = models.CharField(max_length=255, verbose_name="Quiz nomi")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Guruh")
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'}, verbose_name="O'qituvchi")
    time_limit = models.PositiveIntegerField(default=30)
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimal ball")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.group.name})"

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Tegishli Quiz")
    text = models.TextField(verbose_name="Savol matni")

    def __str__(self):
        return self.text

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers', verbose_name="Tegishli savol")
    text = models.CharField(max_length=255, verbose_name="Javob matni")
    is_correct = models.BooleanField(default=False, verbose_name="To‘g‘ri javobmi?")

    def __str__(self):
        return f"{self.text} ({'To‘g‘ri' if self.is_correct else 'Noto‘g‘ri'})"


class StudentQuizResult(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    quiz_last_updated = models.DateTimeField()

class StudentAnswer(models.Model):
    result = models.ForeignKey(StudentQuizResult, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.SET_NULL)

def assignment_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    group_name = instance.group.name.replace(" ", "_")
    title_slug = instance.title.replace(" ", "_")
    filename = f'{title_slug}.{ext}'
    return f'assignments/{group_name}/{filename}'

class Assignment(models.Model):
    title = models.CharField(max_length=255, verbose_name="Topshiriq nomi")
    file = models.FileField(upload_to=assignment_upload_path, verbose_name="Topshiriq fayli")
    group = models.ForeignKey("Group", on_delete=models.CASCADE, verbose_name="Guruh")
    teacher = models.ForeignKey("CustomUser", on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    deadline = models.DateTimeField(verbose_name="Topshiriq muddati")
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimal ball")

    def __str__(self):
        return f"{self.title} - {self.group.name}"

class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    file = models.FileField(upload_to='submissions/')
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.PositiveIntegerField(null=True, blank=True)
    def __str__(self):
        return f"{self.student} -> {self.assignment.title}"

class Attendance(models.Model):
    STATUS_CHOICES = (
        ('present', 'Kelgan'),
        ('absent', 'Kelmadi'),
    )

    student = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name='attendances_as_student',
        limit_choices_to={'role': 'student'}
    )
    teacher = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name='attendances_as_teacher',
        limit_choices_to={'role': 'teacher'}
    )
    group = models.ForeignKey("Group", on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} - {self.group.name} - {self.status} - {self.date}"



class SiteSetting(models.Model):
    image = models.ImageField(upload_to='global/', blank=True, null=True)

    def __str__(self):
        return "Sayt sozlamalari (Global rasm)"

    class Meta:
        verbose_name = "Logatip"
        verbose_name_plural = "Logatip"


class ProfileSetting(models.Model):
    image = models.ImageField(upload_to='default/', blank=True, null=True)

    def __str__(self):
        return "Sayt sozlamalari (default rasm)"

    class Meta:
        verbose_name = "Default img"
        verbose_name_plural = "Default img"

class GroupPaymentInfo(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="payment_info")
    course_duration_months = models.PositiveIntegerField(verbose_name="Kurs davomiyligi (oy)")
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Har oy uchun to'lov summasi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_fee(self):
        return self.course_duration_months * self.monthly_fee

    def __str__(self):
        return f"{self.group.name} - {self.monthly_fee} so'm/oy"

class StudentPayment(models.Model):
    MONTH_CHOICES = [
        ("Yanvar", "Yanvar"),
        ("Fevral", "Fevral"),
        ("Mart", "Mart"),
        ("Aprel", "Aprel"),
        ("May", "May"),
        ("Iyun", "Iyun"),
        ("Iyul", "Iyul"),
        ("Avgust", "Avgust"),
        ("Sentabr", "Sentabr"),
        ("Oktabr", "Oktabr"),
        ("Noyabr", "Noyabr"),
        ("Dekabr", "Dekabr"),
    ]

    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    month = models.CharField(max_length=20, choices=MONTH_CHOICES)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} - {self.month} - {self.amount_paid}"
