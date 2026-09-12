from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from main.validators import validate_image_file, validate_document_file, validate_pdf_file, validate_video_file


def user_profile_image_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{instance.username}_profile.{ext}'
    return f'profiles/{filename}'


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', "Administrator"),
        ('reception', "Retseptsiya (Sub-admin)"),
        ('teacher', "O'qituvchi"),
        ('student', "O'quvchi"),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, db_index=True)
    profile_image = models.ImageField(upload_to=user_profile_image_path, blank=True, null=True, validators=[validate_image_file])
    phone_number = models.CharField(max_length=20, verbose_name="Telefon raqami", blank=False, db_index=True)
    joined_at = models.DateTimeField(verbose_name="Qo'shilgan vaqti", default=timezone.now, db_index=True)
    subjects = models.ManyToManyField('Subject', blank=True, related_name='teachers', verbose_name="Dars beradigan fanlari")
    telegram_chat_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Telegram Chat ID", db_index=True)
    telegram_token = models.CharField(max_length=50, blank=True, null=True, verbose_name="Telegram Token", db_index=True)
    telegram_otp_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="Telegram OTP Code", db_index=True)
    telegram_otp_created_at = models.DateTimeField(blank=True, null=True, verbose_name="Telegram OTP Created At")
    subadmin_permissions = models.JSONField(default=list, blank=True, verbose_name="Sub-admin huquqlari")
    
    # Hamyon
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Hamyon balansi")

    # Onboarding & Shaxsiy ma'lumotlar roziligi (O'RQ-547)
    middle_name = models.CharField(max_length=150, blank=True, verbose_name="Sharifi / Otasining ismi", default='')
    is_profile_completed = models.BooleanField(default=False, verbose_name="Profil to'ldirilganmi", db_index=True)
    terms_accepted = models.BooleanField(default=False, verbose_name="Nizomga rozilik berilganmi", db_index=True)
    terms_accepted_at = models.DateTimeField(blank=True, null=True, verbose_name="Rozilik berilgan sana")
    terms_accepted_ip = models.CharField(max_length=50, blank=True, null=True, verbose_name="Rozilik berilgan IP")

    def get_full_name(self):
        """
        Foydalanuvchining to'liq F.I.Sh (Familiya Ism Sharif) ni qaytaradi.
        """
        parts = [self.last_name, self.first_name, self.middle_name]
        full_name = " ".join(part for part in parts if part).strip()
        return full_name or self.username

    def get_full_name_reverse(self):
        """
        Ism Familiya Sharif formatida qaytaradi.
        """
        parts = [self.first_name, self.last_name, self.middle_name]
        return " ".join(part for part in parts if part).strip() or self.username

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"


class Subject(models.Model):
    name = models.CharField(max_length=100, verbose_name="Fan nomi", unique=True, db_index=True)
    description = models.TextField(blank=True, null=True, verbose_name="Fan haqida ma'lumot")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Fan"
        verbose_name_plural = "Fanlar"


class SubjectMaterial(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='materials', verbose_name="Fan", db_index=True)
    title = models.CharField(max_length=255, verbose_name="Material nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    file = models.FileField(upload_to='subject_materials/', verbose_name="Fayl", validators=[validate_document_file])
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Yuklovchi", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqti", db_index=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"

    class Meta:
        verbose_name = "Fan materiali"
        verbose_name_plural = "Fan materiallari"


class Group(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups', verbose_name="Fan", db_index=True)
    students = models.ManyToManyField(CustomUser, through='GroupStudentMembership', related_name='student_groups', limit_choices_to={'role': 'student'})
    teachers = models.ManyToManyField(CustomUser, related_name='teachers_groups', limit_choices_to={'role': 'teacher'})
    created_at = models.DateTimeField(verbose_name='Guruh ochilgan vaqti', default=timezone.now, db_index=True)
    
    # O'qituvchi maoshi parametrlari
    salary_type = models.CharField(max_length=15, choices=(('percent', "Foizli (Tushumdan)"), ('fixed', "Darsbay (Ruxsat etilgan fixed)")), default='percent', verbose_name="Maosh turi")
    salary_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Maosh tarifi (Foiz yoki Fix summa)")

    def __str__(self):
        return self.name


class GroupStudentMembership(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, db_index=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)

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
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='schedules', db_index=True)
    teacher = models.ForeignKey(CustomUser,
                                on_delete=models.CASCADE,
                                related_name='schedules',
                                limit_choices_to={'role': 'teacher'},
                                db_index=True)
    day = models.CharField(max_length=10, choices=DAYS_OF_WEEK, db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"{self.group.name} - {self.get_day_display()} ({self.start_time} - {self.end_time})"


class Quiz(models.Model):
    title = models.CharField(max_length=255, verbose_name="Quiz nomi")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name="Guruh", db_index=True)
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'}, verbose_name="O'qituvchi", db_index=True)
    time_limit = models.PositiveIntegerField(default=30)
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimal ball")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.group.name})"


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Tegishli Quiz", db_index=True)
    text = models.TextField(verbose_name="Savol matni")

    def __str__(self):
        return self.text


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers', verbose_name="Tegishli savol", db_index=True)
    text = models.CharField(max_length=255, verbose_name="Javob matni")
    is_correct = models.BooleanField(default=False, verbose_name="To‘g‘ri javobmi?", db_index=True)

    def __str__(self):
        return f"{self.text} ({'To‘g‘ri' if self.is_correct else 'Noto‘g‘ri'})"


class StudentQuizResult(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, db_index=True)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, db_index=True)
    score = models.IntegerField(db_index=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    quiz_last_updated = models.DateTimeField()


class StudentAnswer(models.Model):
    result = models.ForeignKey(StudentQuizResult, related_name='answers', on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, db_index=True)
    selected_answer = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.SET_NULL, db_index=True)


from django.utils.text import get_valid_filename


def assignment_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    group_name = get_valid_filename(instance.group.name)
    title_slug = get_valid_filename(instance.title)
    filename = f'{title_slug}.{ext}'
    return f'assignments/{group_name}/{filename}'


class Assignment(models.Model):
    title = models.CharField(max_length=255, verbose_name="Topshiriq nomi")
    file = models.FileField(upload_to=assignment_upload_path, verbose_name="Topshiriq fayli", validators=[validate_document_file])
    group = models.ForeignKey("Group", on_delete=models.CASCADE, verbose_name="Guruh", db_index=True)
    teacher = models.ForeignKey("CustomUser", on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'}, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti", db_index=True)
    deadline = models.DateTimeField(verbose_name="Topshiriq muddati", db_index=True)
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimal ball")

    def __str__(self):
        return f"{self.title} - {self.group.name}"


class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions', db_index=True)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, db_index=True)
    file = models.FileField(upload_to='submissions/', validators=[validate_document_file])
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    grade = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    feedback = models.TextField(null=True, blank=True, verbose_name="O'qituvchi izohi")

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
        limit_choices_to={'role': 'student'},
        db_index=True
    )
    teacher = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name='attendances_as_teacher',
        limit_choices_to={'role': 'teacher'},
        db_index=True
    )
    group = models.ForeignKey("Group", on_delete=models.CASCADE, db_index=True)
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('student', 'group', 'date')

    def __str__(self):
        return f"{self.student} - {self.group.name} - {self.status} - {self.date}"


class SiteSetting(models.Model):
    site_name = models.CharField(max_length=255, default="Tizim", verbose_name="Brend nomi / Sayt nomi")
    image = models.ImageField(upload_to='global/', blank=True, null=True, validators=[validate_image_file], verbose_name="Logotip")
    login_bg_image = models.ImageField(upload_to='global/', blank=True, null=True, validators=[validate_image_file], verbose_name="Login fon rasmi")
    
    # SMS Xizmati (Eskiz.uz) sozlamalari
    eskiz_email = models.CharField(max_length=255, blank=True, null=True, verbose_name="Eskiz.uz Email / Login")
    eskiz_password = models.CharField(max_length=255, blank=True, null=True, verbose_name="Eskiz.uz Yashirin kalit / Parol")
    eskiz_from_name = models.CharField(max_length=50, default="4546", verbose_name="Eskiz Alfa-nom (Yuboruvchi)")
    sms_enabled = models.BooleanField(default=False, verbose_name="SMS xizmati faolmi")
    sms_on_register = models.BooleanField(default=True, verbose_name="Ro'yxatdan o'tganda login/parol yuborish")
    sms_on_payment = models.BooleanField(default=True, verbose_name="To'lov qabul qilinganda SMS yuborish")
    sms_on_absence = models.BooleanField(default=True, verbose_name="Darsga kelmaganda SMS yuborish")

    # Telegram Bot sozlamalari
    telegram_bot_token = models.CharField(max_length=255, blank=True, null=True, verbose_name="Telegram Bot Token")
    telegram_bot_username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Telegram Bot Username")
    telegram_enabled = models.BooleanField(default=True, verbose_name="Telegram Bot xizmati faolmi")
    telegram_on_register = models.BooleanField(default=True, verbose_name="Ro'yxatdan o'tganda Telegram orqali login/parol yuborish")
    telegram_on_payment = models.BooleanField(default=True, verbose_name="To'lov qabul qilinganda Telegram yuborish")
    telegram_on_absence = models.BooleanField(default=True, verbose_name="Darsga kelmaganda Telegram yuborish")

    def __str__(self):
        return f"Sayt sozlamalari ({self.site_name})"

    class Meta:
        verbose_name = "Logatip va Sozlamalar"
        verbose_name_plural = "Logatip va Sozlamalar"


class ProfileSetting(models.Model):
    image = models.ImageField(upload_to='default/', blank=True, null=True, validators=[validate_image_file])

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

    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, db_index=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, db_index=True)
    month = models.CharField(max_length=20, choices=MONTH_CHOICES, db_index=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.student} - {self.month} - {self.amount_paid}"


class AIQuiz(models.Model):
    LEVEL_CHOICES = (
        ('beginner', 'Boshlang\'ich (Beginner / A1-A2)'),
        ('intermediate', 'O\'rta (Intermediate / B1-B2)'),
        ('advanced', 'Yuqori (Advanced / C1-C2)'),
    )
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='ai_quizzes', db_index=True)
    title = models.CharField(max_length=255, verbose_name="Mavzu nomi")
    categories = models.TextField(verbose_name="Tanlangan kategoriyalar")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, verbose_name="Daraja", db_index=True)
    score = models.IntegerField(null=True, blank=True, verbose_name="To'plangan ball")
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimal ball")
    time_limit = models.PositiveIntegerField(default=10, verbose_name="Bajarish vaqti (daqiqa)")
    ai_feedback = models.TextField(null=True, blank=True, verbose_name="AI Natija Tahlili")
    is_completed = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student} - {self.title} ({self.level})"


class AIQuestion(models.Model):
    quiz = models.ForeignKey(AIQuiz, on_delete=models.CASCADE, related_name='questions', db_index=True)
    text = models.TextField(verbose_name="Savol matni")
    correct_explanation = models.TextField(null=True, blank=True, verbose_name="To'g'ri javob izohi")

    def __str__(self):
        return self.text[:50]


class AIAnswer(models.Model):
    question = models.ForeignKey(AIQuestion, on_delete=models.CASCADE, related_name='answers', db_index=True)
    text = models.CharField(max_length=255, verbose_name="Javob varianti")
    is_correct = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return self.text


class StudentAIAnswer(models.Model):
    quiz = models.ForeignKey(AIQuiz, on_delete=models.CASCADE, related_name='student_answers', db_index=True)
    question = models.ForeignKey(AIQuestion, on_delete=models.CASCADE, db_index=True)
    selected_answer = models.ForeignKey(AIAnswer, on_delete=models.CASCADE, null=True, blank=True, db_index=True)


class StudentAIPlan(models.Model):
    student = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='ai_plan', limit_choices_to={'role': 'student'})
    advice = models.TextField(verbose_name="AI Achchiq Tanbehi")
    plan = models.TextField(verbose_name="Kelgusi kunlar rejasi")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.username} - AI Reja"


class SystemAnnouncement(models.Model):
    TARGET_CHOICES = (
        ('all', 'Barcha foydalanuvchilar'),
        ('teacher', "Faqat o'qituvchilar"),
        ('student', "Faqat o'quvchilar"),
    )
    CATEGORY_CHOICES = (
        ('always_show', "Doimiy ko'rsatish (Banner)"),
        ('one_time', "Tizimga 1-marta kirganda (Bir martalik)"),
    )
    title = models.CharField(max_length=255, verbose_name="Sarlavha")
    message = models.TextField(verbose_name="Xabar matni")
    target_role = models.CharField(max_length=15, choices=TARGET_CHOICES, default='all', verbose_name="Kimlar uchun", db_index=True)
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='always_show', verbose_name="Turkum", db_index=True)
    start_time = models.DateTimeField(default=timezone.now, verbose_name="Boshlanish vaqti", db_index=True)
    end_time = models.DateTimeField(verbose_name="Tugash vaqti", db_index=True)
    is_active = models.BooleanField(default=True, verbose_name="Faol", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return self.title


class GroupLesson(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='lessons', db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    topic = models.CharField(max_length=255, verbose_name="Dars mavzusi")
    notes = models.TextField(blank=True, null=True, verbose_name="Konspekt / Dars rejasi")
    homework = models.TextField(blank=True, null=True, verbose_name="Uyga vazifa")
    file = models.FileField(upload_to='lessons/materials/', blank=True, null=True, verbose_name="Dars materiali", validators=[validate_document_file])
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.group.name} - {self.topic} ({self.date})"


class AuditLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs', db_index=True)
    action = models.CharField(max_length=100, verbose_name="Harakat turi", db_index=True)
    description = models.TextField(verbose_name="Tafsilot")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Vaqti", db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP Manzil")

    def __str__(self):
        return f"{self.user} - {self.action} ({self.timestamp})"


class UserSession(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sessions', db_index=True)
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_type = models.CharField(max_length=50, default='Unknown')
    browser = models.CharField(max_length=50, default='Unknown')
    os = models.CharField(max_length=50, default='Unknown')
    location = models.CharField(max_length=255, default='Unknown')
    last_activity = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.user} - {self.device_type} ({self.ip_address})"


def video_upload_path(instance, filename):
    from django.utils.text import get_valid_filename
    ext = filename.split('.')[-1]
    group_name = get_valid_filename(instance.group.name)
    title_slug = get_valid_filename(instance.title)
    filename = f'{title_slug}.{ext}'
    return f'videos/{group_name}/{filename}'


class GroupVideo(models.Model):
    title = models.CharField(max_length=255, verbose_name="Dars sarlavhasi")
    description = models.TextField(blank=True, null=True, verbose_name="Dars tavsifi")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='videos', verbose_name="Guruh", db_index=True)
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='uploaded_videos', limit_choices_to={'role': 'teacher'}, null=True, blank=True, verbose_name="O'qituvchi", db_index=True)
    video_file = models.FileField(upload_to=video_upload_path, blank=True, null=True, verbose_name="Video fayl", validators=[validate_video_file])
    youtube_link = models.URLField(blank=True, null=True, verbose_name="YouTube havola")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqt", db_index=True)

    def __str__(self):
        return f"{self.title} - {self.group.name}"

    def get_youtube_embed(self):
        if not self.youtube_link:
            return None
        import re
        regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        match = re.search(regex, self.youtube_link)
        if match:
            return f"https://www.youtube.com/embed/{match.group(1)}"
        return self.youtube_link


class DTMQuestionPool(models.Model):
    subject = models.CharField(max_length=100, verbose_name="Fan nomi", db_index=True)
    difficulty = models.IntegerField(default=2, verbose_name="Qiyinlik darajasi (1: Qiyin, 2: O'rtacha, 3: Oson)", db_index=True)
    is_compulsory = models.BooleanField(default=False, verbose_name="Majburiy fan savoli", db_index=True)
    text = models.TextField(verbose_name="Savol matni")

    def __str__(self):
        return f"{self.subject} ({'Majburiy' if self.is_compulsory else 'Blok'}) - {self.text[:50]}"


class DTMAnswerPool(models.Model):
    question = models.ForeignKey(DTMQuestionPool, on_delete=models.CASCADE, related_name='answers', db_index=True)
    text = models.CharField(max_length=255, verbose_name="Variant matni")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri javob", db_index=True)

    def __str__(self):
        return f"{'Correct: ' if self.is_correct else ''}{self.text[:50]}"


class DTMExam(models.Model):
    title = models.CharField(max_length=255, verbose_name="Imtihon nomi")
    registration_deadline = models.DateTimeField(verbose_name="Ro'yxatdan o'tish muddati", db_index=True)
    exam_date = models.DateTimeField(verbose_name="Imtihon vaqti", db_index=True)
    block1_questions_count = models.IntegerField(default=30, verbose_name="1-blok savollar soni")
    block1_score = models.FloatField(default=3.1, verbose_name="1-blok har bir savol bali")
    block2_questions_count = models.IntegerField(default=30, verbose_name="2-blok savollar soni")
    block2_score = models.FloatField(default=2.1, verbose_name="2-blok har bir savol bali")
    compulsory_questions_count = models.IntegerField(default=10, verbose_name="Majburiy fan har bir savol bali")
    compulsory_score = models.FloatField(default=1.1, verbose_name="Majburiy fan har bir savol bali")
    is_active = models.BooleanField(default=True, verbose_name="Faol", db_index=True)

    def __str__(self):
        return self.title


class DTMRegistration(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='dtm_registrations', db_index=True)
    exam = models.ForeignKey(DTMExam, on_delete=models.CASCADE, related_name='registrations', db_index=True)
    block1_subject = models.CharField(max_length=100, verbose_name="1-blok fani", db_index=True)
    block2_subject = models.CharField(max_length=100, verbose_name="2-blok fani", db_index=True)
    take_compulsory = models.BooleanField(default=True, verbose_name="Majburiy fanlarni topshiradi")
    booklet_number = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Kitobcha raqami", db_index=True)
    booklet_file = models.FileField(upload_to='dtm_booklets/', null=True, blank=True, verbose_name="Savollar kitobchasi PDF", validators=[validate_pdf_file])
    booklet_answers_key = models.TextField(null=True, blank=True, verbose_name="Kitobcha javoblari kaliti")
    registered_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.exam.title}"


class StudentDTMExamResult(models.Model):
    registration = models.OneToOneField(DTMRegistration, on_delete=models.CASCADE, related_name='result')
    score_block1 = models.FloatField(default=0.0, verbose_name="1-blok bali")
    score_block2 = models.FloatField(default=0.0, verbose_name="2-blok bali")
    score_compulsory = models.FloatField(default=0.0, verbose_name="Majburiy fanlar bali")
    total_score = models.FloatField(default=0.0, verbose_name="Umumiy ball", db_index=True)
    student_answers_raw = models.TextField(null=True, blank=True, verbose_name="Talaba javoblari")
    processed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.registration.student.get_full_name()} - Natija: {self.total_score}"


class SystemErrorLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='error_logs', db_index=True)
    url_path = models.CharField(max_length=255, verbose_name="Xatolik yuz bergan URL", db_index=True)
    error_message = models.TextField(verbose_name="Xatolik xabari")
    traceback = models.TextField(verbose_name="Traceback tafsiloti")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Vaqti", db_index=True)
    is_resolved = models.BooleanField(default=False, verbose_name="Hal etildi", db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Hal etilgan vaqt")
    resolved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_errors', verbose_name="Hal etgan shaxs")

    def __str__(self):
        return f"Error on {self.url_path} ({self.timestamp})"


class LockedPage(models.Model):
    url_path = models.CharField(max_length=255, unique=True, verbose_name="Bloklangan URL", db_index=True)
    reason = models.TextField(verbose_name="Bloklanish sababi")
    locked_at = models.DateTimeField(auto_now_add=True, verbose_name="Bloklangan vaqt")
    is_active = models.BooleanField(default=True, verbose_name="Faol bloklash", db_index=True)

    def __str__(self):
        return f"{self.url_path} - {'Blocked' if self.is_active else 'Open'}"


class Book(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='books', verbose_name="Fan", db_index=True)
    title = models.CharField(max_length=255, verbose_name="Kitob nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Tavsif")
    file = models.FileField(upload_to='books/pdfs/', verbose_name="PDF Fayl", validators=[validate_pdf_file])
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Yuklovchi", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqti", db_index=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"

    class Meta:
        verbose_name = "Kitob"
        verbose_name_plural = "Kitoblar"
        ordering = ['-created_at']


class TeacherSalaryPayment(models.Model):
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='salary_payments', limit_choices_to={'role': 'teacher'}, verbose_name="O'qituvchi", db_index=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Guruh")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="To'langan summa")
    month = models.CharField(max_length=20, verbose_name="Qaysi oy uchun", db_index=True) # masalan, "August 2026"
    paid_at = models.DateTimeField(auto_now_add=True, verbose_name="To'langan vaqti", db_index=True)
    paid_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_salaries', verbose_name="Tasdiqlovchi")
    notes = models.TextField(blank=True, null=True, verbose_name="Izoh")

    def __str__(self):
        return f"{self.teacher.first_name} {self.teacher.last_name} - {self.amount} ({self.month})"

    class Meta:
        verbose_name = "O'qituvchi maoshi to'lovi"
        verbose_name_plural = "O'qituvchi maoshi to'lovlari"
        ordering = ['-paid_at']


class WalletTransaction(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='wallet_transactions', limit_choices_to={'role': 'student'}, verbose_name="O'quvchi", db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Summa") # Musbat - to'ldirish, Manfiy - yechish
    transaction_type = models.CharField(max_length=20, choices=(('top_up', "Balansni to'ldirish"), ('payment', "Guruh uchun to'lov")), verbose_name="Turi", db_index=True)
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Tavsif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vaqti", db_index=True)

    def __str__(self):
        return f"{self.student.username} - {self.amount} ({self.get_transaction_type_display()})"

    class Meta:
        verbose_name = "Hamyon tranzaksiyasi"
        verbose_name_plural = "Hamyon tranzaksiyalari"
        ordering = ['-created_at']


class PaymentOrder(models.Model):
    STATUS_CHOICES = (
        ('waiting', "Kutilmoqda"),
        ('paid', "To'landi"),
        ('cancelled', "Bekor qilindi"),
        ('failed', "Xatolik"),
    )
    PROVIDER_CHOICES = (
        ('payme', "Payme"),
        ('click', "Click"),
    )
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payment_orders', limit_choices_to={'role': 'student'}, verbose_name="O'quvchi", db_index=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Guruh", db_index=True)
    month = models.CharField(max_length=20, null=True, blank=True, verbose_name="Qaysi oy uchun", db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Summa (so'm)")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, verbose_name="To'lov tizimi", db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting', verbose_name="Holati", db_index=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="Tranzaksiya ID (Tizim)", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti", db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="To'langan vaqti", db_index=True)

    def __str__(self):
        return f"Order #{self.id} - {self.student.username} - {self.amount} ({self.provider}) - {self.status}"

    class Meta:
        verbose_name = "To'lov buyurtmasi"
        verbose_name_plural = "To'lov buyurtmalari"
        ordering = ['-created_at']


class PaymeTransaction(models.Model):
    STATE_CREATED = 1
    STATE_COMPLETED = 2
    STATE_CANCELLED = -1
    STATE_CANCELLED_AFTER_COMPLETE = -2

    order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='payme_transactions', verbose_name="Buyurtma", db_index=True)
    transaction_id = models.CharField(max_length=255, unique=True, verbose_name="Payme Tranzaksiya ID", db_index=True)
    time = models.BigIntegerField(verbose_name="Payme Vaqti (ms)", db_index=True)
    amount = models.BigIntegerField(verbose_name="Summa (tiyinda)")
    state = models.IntegerField(default=1, verbose_name="Holat kodi", db_index=True)
    reason = models.IntegerField(null=True, blank=True, verbose_name="Bekor qilish sababi")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    performed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payme {self.transaction_id} (State: {self.state})"

    class Meta:
        verbose_name = "Payme Tranzaksiyasi"
        verbose_name_plural = "Payme Tranzaksiyalari"


class ClickTransaction(models.Model):
    order = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name='click_transactions', verbose_name="Buyurtma", db_index=True)
    click_trans_id = models.CharField(max_length=255, unique=True, verbose_name="Click Tranzaksiya ID", db_index=True)
    service_id = models.CharField(max_length=50, verbose_name="Xizmat ID")
    click_paydoc_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="Click To'lov Hujjati ID")
    merchant_trans_id = models.CharField(max_length=255, verbose_name="Merchant Tranzaksiya ID", db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Summa")
    action = models.IntegerField(verbose_name="Amal kodi (0: Prepare, 1: Complete)", db_index=True)
    error = models.IntegerField(default=0, verbose_name="Xatolik kodi")
    status = models.CharField(max_length=50, default='waiting', verbose_name="Holati", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Click {self.click_trans_id} (Status: {self.status})"

    class Meta:
        verbose_name = "Click Tranzaksiyasi"
        verbose_name_plural = "Click Tranzaksiyalari"


