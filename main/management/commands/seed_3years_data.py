import random
from datetime import datetime, timedelta, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from main.models import (
    Subject, Group, GroupStudentMembership, Schedule,
    GroupPaymentInfo, StudentPayment, Attendance, GroupLesson,
    Quiz, Question, Answer, StudentQuizResult, StudentAnswer,
    Assignment, AssignmentSubmission, SiteSetting, SystemAnnouncement,
    DTMExam, DTMRegistration, StudentDTMExamResult
)

User = get_user_model()

class Command(BaseCommand):
    help = "3 yillik (5-10 barobar ko'p) ma'lumotlarni ultra-tezkor yuklash"

    def handle(self, *args, **options):
        self.stdout.write("=== 3 YILLIK ULTRA-TEZKOR MA'LUMOTLARNI YUKLASH BOSHLANDI ===")

        teacher_pwd = make_password('teacher123')
        student_pwd = make_password('student123')

        # 1. Admin
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Admin',
                'last_name': 'Boshqaruvchi',
                'email': 'admin@fumaisak.uz',
                'phone_number': '+998901234567',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if not admin_user.check_password('admin123'):
            admin_user.set_password('admin123')
            admin_user.save()

        SiteSetting.objects.get_or_create(site_name="FUMA ISAK O'quv Markazi")

        # 2. Fanlar (12 ta)
        subjects_data = [
            ("Matematika", "Oliy matematika, DTM va Algebra tayyorlov kursi"),
            ("Fizika", "Nazariy va amaliy fizika hamda masalalar yechish"),
            ("Ingliz tili (IELTS / CEFR)", "Grammar, Speaking, Writing va Mock testlar"),
            ("IT & Dasturlash (Python)", "Web dasturlash, Backend va Django freymvorki"),
            ("Kimyo", "Anorganik va organik kimyo nazariyasi va masalalari"),
            ("Biologiya", "Odam anatomiyasi, botanika va genetika"),
            ("Ona tili va Adabiyot", "O'zbek tili grammatikasi va adabiyot tahlili"),
            ("Nemis tili (Goethe/TestDaF)", "A1-C1 darajalarigacha intensiv nemis tili"),
            ("Rus tili (TORFL)", "So'zlashuv va biznes rus tili"),
            ("SAT / GMAT Math", "Xalqaro universitetlar uchun arifmetika va mantiq"),
            ("Data Science & AI", "Python, Pandas, Machine Learning asoslari"),
            ("Kiberxavfsizlik (Ethical Hacking)", "Tarmoq xavfsizligi va Linux tizimlari"),
        ]

        subjects = {}
        for name, desc in subjects_data:
            subj, _ = Subject.objects.get_or_create(name=name, defaults={'description': desc})
            subjects[name] = subj

        # 3. O'qituvchilar (15 nafar)
        teachers_info = [
            ("anvar_math", "Anvar", "Qodirov", "+998911112233", ["Matematika", "SAT / GMAT Math"]),
            ("jasur_phys", "Jasur", "Alimov", "+998912223344", ["Fizika"]),
            ("nilufar_eng", "Nilufar", "Saidova", "+998913334455", ["Ingliz tili (IELTS / CEFR)"]),
            ("sardor_it", "Sardorbek", "Karimov", "+998914445566", ["IT & Dasturlash (Python)", "Data Science & AI"]),
            ("dilnoza_chem", "Dilnoza", "Rahmonova", "+998915556677", ["Kimyo", "Biologiya"]),
            ("bekzod_lang", "Bekzod", "Toshmatov", "+998916667788", ["Ona tili va Adabiyot"]),
            ("shahnoza_ger", "Shahnoza", "Ergasheva", "+998917778899", ["Nemis tili (Goethe/TestDaF)"]),
            ("elena_rus", "Elena", "Petrova", "+998918889900", ["Rus tili (TORFL)"]),
            ("utkur_cyber", "O'tkir", "Jo'rayev", "+998919990011", ["Kiberxavfsizlik (Ethical Hacking)"]),
            ("kamol_math2", "Kamoliddin", "Sobirov", "+998910001122", ["Matematika"]),
            ("feruza_eng2", "Feruza", "Akramova", "+998910002233", ["Ingliz tili (IELTS / CEFR)"]),
            ("rustam_it2", "Rustam", "Nazarov", "+998910003344", ["IT & Dasturlash (Python)"]),
            ("shohrux_phys2", "Shohrux", "Xamidov", "+998910004455", ["Fizika"]),
            ("malika_bio2", "Malika", "Zokirova", "+998910005566", ["Biologiya"]),
            ("azamat_sat", "Azamat", "Qosimov", "+998910006677", ["SAT / GMAT Math"]),
        ]

        teachers = []
        for username, fname, lname, phone, subj_names in teachers_info:
            t, t_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'phone_number': phone,
                    'role': 'teacher',
                    'email': f"{username}@fumaisak.uz",
                    'password': teacher_pwd,
                    'is_staff': True
                }
            )
            for sn in subj_names:
                if sn in subjects:
                    t.subjects.add(subjects[sn])
            teachers.append(t)

        # 4. O'quvchilar (200 nafar bulk)
        first_names = ["Otabek", "Shaxzod", "Madina", "Sevinch", "Diyorbek", "Bobur", "Javohir", "Kamola", "Malika", "Sirojiddin", "Rustam", "Zilola", "Nodira", "Sherzod", "Azizbek", "Gulnoza", "Asal", "Sarvar", "Farrux", "Lobar"]
        last_names = ["Ismoilov", "Karimov", "Tursunov", "Abdullayev", "Xalilov", "Nazarov", "Yusupov", "Olimov", "Sultonov", "Rahimov", "Vahobov", "Hasanov", "Qosimov", "Jo'rayev", "Mirzayev"]

        existing_students = set(User.objects.filter(role='student').values_list('username', flat=True))
        new_students_to_create = []

        for i in range(1, 201):
            uname = f"student_{i}"
            if uname not in existing_students:
                fname = first_names[(i - 1) % len(first_names)]
                lname = last_names[(i - 1) % len(last_names)]
                phone = f"+99890{1000000 + i * 1111}"
                u = User(
                    username=uname,
                    first_name=fname,
                    last_name=lname,
                    phone_number=phone,
                    role='student',
                    email=f"{uname}@mail.uz",
                    password=student_pwd,
                    joined_at=timezone.now() - timedelta(days=random.randint(300, 1000))
                )
                new_students_to_create.append(u)

        if new_students_to_create:
            User.objects.bulk_create(new_students_to_create, ignore_conflicts=True)

        students = list(User.objects.filter(role='student').order_by('id'))
        self.stdout.write(f"[OK] {len(students)} ta o'quvchi tayyor.")

        # 5. Guruhlar (24 ta guruh)
        groups_config = [
            ("MATEMATIKA-101", subjects["Matematika"], teachers[0], 500000),
            ("MATEMATIKA-202", subjects["Matematika"], teachers[9], 520000),
            ("FIZIKA-INTENSIV", subjects["Fizika"], teachers[1], 450000),
            ("FIZIKA-PRO", subjects["Fizika"], teachers[12], 480000),
            ("IELTS-MASTER", subjects["Ingliz tili (IELTS / CEFR)"], teachers[2], 600000),
            ("IELTS-ADVANCED", subjects["Ingliz tili (IELTS / CEFR)"], teachers[10], 650000),
            ("PYTHON-BACKEND", subjects["IT & Dasturlash (Python)"], teachers[3], 700000),
            ("DJANGO-PRO", subjects["IT & Dasturlash (Python)"], teachers[11], 750000),
            ("KIMYO-BIO-MED", subjects["Kimyo"], teachers[4], 550000),
            ("KIMYO-OLYMPIAD", subjects["Kimyo"], teachers[4], 580000),
            ("BIOLOGIYA-INTENSIV", subjects["Biologiya"], teachers[13], 500000),
            ("ONA-TILI-DTM", subjects["Ona tili va Adabiyot"], teachers[5], 400000),
            ("GERMAN-A1-B2", subjects["Nemis tili (Goethe/TestDaF)"], teachers[6], 620000),
            ("RUSSIAN-BUSINESS", subjects["Rus tili (TORFL)"], teachers[7], 500000),
            ("SAT-QUANT-MASTER", subjects["SAT / GMAT Math"], teachers[14], 800000),
            ("DATA-SCIENCE-AI", subjects["Data Science & AI"], teachers[3], 850000),
            ("CYBER-SECURITY-101", subjects["Kiberxavfsizlik (Ethical Hacking)"], teachers[8], 900000),
            ("MATEMATIKA-303", subjects["Matematika"], teachers[0], 550000),
            ("FIZIKA-BASIC", subjects["Fizika"], teachers[1], 420000),
            ("IELTS-FOUNDATION", subjects["Ingliz tili (IELTS / CEFR)"], teachers[2], 550000),
            ("PYTHON-BEGINNER", subjects["IT & Dasturlash (Python)"], teachers[3], 650000),
            ("KIMYO-BASIC", subjects["Kimyo"], teachers[4], 500000),
            ("BIOLOGIYA-BASIC", subjects["Biologiya"], teachers[13], 480000),
            ("ONA-TILI-ESSAY", subjects["Ona tili va Adabiyot"], teachers[5], 420000),
        ]

        groups = []
        memberships_to_create = []
        payments_to_create = []
        months_names = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]

        GroupStudentMembership.objects.all().delete()
        StudentPayment.objects.all().delete()

        for g_idx, (gname, subj, main_teacher, fee) in enumerate(groups_config):
            grp, _ = Group.objects.get_or_create(
                name=gname,
                defaults={
                    'subject': subj,
                    'created_at': timezone.now() - timedelta(days=1000)
                }
            )
            grp.teachers.add(main_teacher)

            GroupPaymentInfo.objects.update_or_create(
                group=grp,
                defaults={'course_duration_months': 36, 'monthly_fee': fee}
            )

            # Assign 10-15 students per group
            start_st = (g_idx * 8) % len(students)
            assigned_students = students[start_st : start_st + 12]

            for st in assigned_students:
                memberships_to_create.append(
                    GroupStudentMembership(
                        student=st,
                        group=grp,
                        joined_at=timezone.now() - timedelta(days=950)
                    )
                )

                # 3 yillik (36 oylik) to'lovlar
                for y_idx in range(3):
                    for m_idx, m_name in enumerate(months_names):
                        if (g_idx + m_idx + y_idx) % 4 != 0:
                            payments_to_create.append(
                                StudentPayment(
                                    student=st,
                                    group=grp,
                                    month=f"{m_name} {2024 + y_idx}",
                                    amount_paid=fee
                                )
                            )
            groups.append(grp)

        GroupStudentMembership.objects.bulk_create(memberships_to_create, ignore_conflicts=True)
        StudentPayment.objects.bulk_create(payments_to_create, ignore_conflicts=True)
        self.stdout.write(f"[OK] {len(groups)} ta guruh va {len(payments_to_create)} ta 3 yillik to'lovlar yaratildi.")

        # 6. Dars Jadvallari
        Schedule.objects.all().delete()
        schedules_to_create = []
        for i, grp in enumerate(groups):
            teacher = grp.teachers.first()
            if i % 2 == 0:
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='monday', start_time=time(14,0), end_time=time(16,0)))
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='wednesday', start_time=time(14,0), end_time=time(16,0)))
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='friday', start_time=time(14,0), end_time=time(16,0)))
            else:
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='tuesday', start_time=time(10,0), end_time=time(12,0)))
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='thursday', start_time=time(10,0), end_time=time(12,0)))
                schedules_to_create.append(Schedule(group=grp, teacher=teacher, day='saturday', start_time=time(10,0), end_time=time(12,0)))
        Schedule.objects.bulk_create(schedules_to_create)

        # 7. 3 YILLIK DARSLAR VA DAVOMATLAR
        GroupLesson.objects.all().delete()
        Attendance.objects.all().delete()

        lessons_to_create = []
        attendance_to_create = []

        topics_list = [
            "Kirish va asosiy tushunchalar", "Formulalar va tenglamalar",
            "Mavzu bo'yicha masalalar yechish", "Mustahkamlash darsi",
            "Chuqurlashtirilgan nazariya", "Oraliq nazorat testlari",
            "Murakkab misollar tahlili", "Yakuniy xulosalar va umumlashtirish"
        ]

        start_date = timezone.now().date() - timedelta(days=900)
        end_date = timezone.now().date()

        for grp_idx, grp in enumerate(groups):
            grp_students = list(grp.students.all())
            teacher = grp.teachers.first()
            curr_date = start_date
            lesson_num = 1

            while curr_date <= end_date:
                is_lesson_day = (curr_date.weekday() in [0, 2, 4]) if (grp_idx % 2 == 0) else (curr_date.weekday() in [1, 3, 5])
                if is_lesson_day:
                    topic_text = f"{grp.subject.name} - {topics_list[lesson_num % len(topics_list)]} ({lesson_num}-dars)"
                    gl = GroupLesson(
                        group=grp,
                        date=curr_date,
                        topic=topic_text,
                        notes=f"{topic_text} bo'yicha konspektlar va asosiy tushunchalar.",
                        homework="Mavzu yuzasidan berilgan 10 ta amaliy topshiriqni bajarish."
                    )
                    lessons_to_create.append(gl)

                    for st_idx, st in enumerate(grp_students):
                        st_status = 'present' if (st_idx + lesson_num) % 7 != 0 else 'absent'
                        attendance_to_create.append(
                            Attendance(
                                student=st,
                                teacher=teacher,
                                group=grp,
                                date=curr_date,
                                status=st_status
                            )
                        )
                    lesson_num += 1
                curr_date += timedelta(days=1)

        GroupLesson.objects.bulk_create(lessons_to_create, batch_size=5000, ignore_conflicts=True)
        Attendance.objects.bulk_create(attendance_to_create, batch_size=10000, ignore_conflicts=True)
        self.stdout.write(f"[OK] 3 yillik {len(lessons_to_create)} ta dars va {len(attendance_to_create)} ta davomat yozuvi yaratildi!")

        # 8. Quizzes & Assignments
        Quiz.objects.all().delete()
        Assignment.objects.all().delete()
        StudentQuizResult.objects.all().delete()
        AssignmentSubmission.objects.all().delete()

        quiz_results_to_create = []
        assignment_subs_to_create = []

        for grp in groups:
            teacher = grp.teachers.first()
            for q_idx in range(1, 4):
                quiz = Quiz.objects.create(
                    title=f"{grp.name} - Nazorat Quizi #{q_idx}",
                    group=grp,
                    teacher=teacher,
                    time_limit=45,
                    max_score=100
                )
                for q_num in range(1, 3):
                    q = Question.objects.create(quiz=quiz, text=f"{grp.subject.name} savoli #{q_num}?")
                    Answer.objects.create(question=q, text="To'g'ri javob", is_correct=True)
                    Answer.objects.create(question=q, text="Noto'g'ri javob", is_correct=False)

                for st in grp.students.all():
                    quiz_results_to_create.append(
                        StudentQuizResult(
                            student=st,
                            quiz=quiz,
                            score=random.randint(70, 100),
                            quiz_last_updated=timezone.now()
                        )
                    )

                assign = Assignment.objects.create(
                    title=f"{grp.name} - Amaliy Uy Vazifasi #{q_idx}",
                    group=grp,
                    teacher=teacher,
                    max_score=100,
                    deadline=timezone.now() + timedelta(days=7)
                )

                for st in grp.students.all():
                    assignment_subs_to_create.append(
                        AssignmentSubmission(
                            assignment=assign,
                            student=st,
                            grade=random.randint(75, 100)
                        )
                    )

        StudentQuizResult.objects.bulk_create(quiz_results_to_create, ignore_conflicts=True)
        AssignmentSubmission.objects.bulk_create(assignment_subs_to_create, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS("=== BARCHA 3 YILLIK (5 BAROBAR KO'P) MA'LUMOTLAR POSTGRESQL (fumaisak_db) BAZASIGA MUVAFFAQIYATLI YUKLANDI! ==="))
