import random
from datetime import datetime, timedelta, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from main.models import (
    Subject, Group, GroupStudentMembership, Schedule,
    GroupPaymentInfo, StudentPayment, Attendance, GroupLesson,
    Quiz, Question, Answer, StudentQuizResult, StudentAnswer,
    Assignment, AssignmentSubmission, SiteSetting, SystemAnnouncement,
    DTMQuestionPool, DTMAnswerPool, DTMExam, DTMRegistration, StudentDTMExamResult
)

User = get_user_model()

class Command(BaseCommand):
    help = "1 yillik o'quv markazi ma'lumotlarini PostgreSQL bazasiga tezkor yuklash"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== 1 YILLIK MA'LUMOTLARNI YUKLASH BOSHLANDI ==="))

        # 1. Superuser / Admin
        admin_user, created = User.objects.get_or_create(
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
        if created or not admin_user.check_password('admin123'):
            admin_user.set_password('admin123')
            admin_user.save()
        self.stdout.write("Admin foydalanuvchi tayyor (admin / admin123).")

        # 2. SiteSetting
        SiteSetting.objects.get_or_create(
            site_name="FUMA ISAK O'quv Markazi",
            defaults={}
        )

        # 3. Fanlar
        subjects_data = [
            ("Matematika", "Oliy matematika va DTM testlariga tayyorlov kursi"),
            ("Fizika", "Nazariy va amaliy fizika hamda masalalar yechish"),
            ("Ingliz tili (IELTS / CEFR)", "Grammatika, Speaking, Writing va Mock testlar"),
            ("IT & Dasturlash (Python)", "Web dasturlash, Backend va Django freymvorki"),
            ("Kimyo", "Anorganik va organik kimyo nazariyasi va masalalari"),
            ("Biologiya", "Odam anatomiyasi, botanika va genetika"),
            ("Ona tili va Adabiyot", "O'zbek tili grammatikasi va adabiyot tahlili"),
        ]

        subjects = {}
        for name, desc in subjects_data:
            subj, _ = Subject.objects.get_or_create(name=name, defaults={'description': desc})
            subjects[name] = subj

        # 4. O'qituvchilar
        teachers_data = [
            ("anvar_math", "Anvar", "Qodirov", "+998911112233", ["Matematika"]),
            ("jasur_phys", "Jasur", "Alimov", "+998912223344", ["Fizika"]),
            ("nilufar_eng", "Nilufar", "Saidova", "+998913334455", ["Ingliz tili (IELTS / CEFR)"]),
            ("sardor_it", "Sardorbek", "Karimov", "+998914445566", ["IT & Dasturlash (Python)"]),
            ("dilnoza_chem", "Dilnoza", "Rahmonova", "+998915556677", ["Kimyo", "Biologiya"]),
            ("bekzod_lang", "Bekzod", "Toshmatov", "+998916667788", ["Ona tili va Adabiyot"]),
        ]

        teachers = []
        for username, fname, lname, phone, subj_names in teachers_data:
            t, t_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'phone_number': phone,
                    'role': 'teacher',
                    'email': f"{username}@fumaisak.uz",
                    'is_staff': True
                }
            )
            if t_created:
                t.set_password('teacher123')
                t.save()
            for sn in subj_names:
                if sn in subjects:
                    t.subjects.add(subjects[sn])
            teachers.append(t)

        # 5. O'quvchilar (40 nafar)
        first_names = ["Otabek", "Shaxzod", "Madina", "Sevinch", "Diyorbek", "Bobur", "Javohir", "Kamola", "Malika", "Sirojiddin", "Rustam", "Zilola", "Nodira", "Sherzod", "Azizbek", "Gulnoza", "Asal", "Sarvar", "Farrux", "Lobar"]
        last_names = ["Ismoilov", "Karimov", "Tursunov", "Abdullayev", "Xalilov", "Nazarov", "Yusupov", "Olimov", "Sultonov", "Rahimov", "Vahobov", "Hasanov", "Qosimov", "Jo'rayev", "Mirzayev"]

        students = []
        for i in range(1, 41):
            fname = first_names[(i - 1) % len(first_names)]
            lname = last_names[(i - 1) % len(last_names)]
            uname = f"student_{i}"
            phone = f"+99890{1000000 + i * 1111}"
            joined = timezone.now() - timedelta(days=360)

            s, s_created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'phone_number': phone,
                    'role': 'student',
                    'joined_at': joined,
                    'email': f"{uname}@mail.uz"
                }
            )
            if s_created:
                s.set_password('student123')
                s.save()
            students.append(s)
        self.stdout.write(f"{len(students)} ta o'quvchi yaratildi (parol: student123).")

        # 6. Guruhlar
        groups_info = [
            ("MATEMATIKA-101", subjects["Matematika"], teachers[0], 500000),
            ("FIZIKA-INTENSIV", subjects["Fizika"], teachers[1], 450000),
            ("IELTS-MASTER", subjects["Ingliz tili (IELTS / CEFR)"], teachers[2], 600000),
            ("PYTHON-BACKEND", subjects["IT & Dasturlash (Python)"], teachers[3], 700000),
            ("KIMYO-BIO-MED", subjects["Kimyo"], teachers[4], 550000),
            ("ONA-TILI-DTM", subjects["Ona tili va Adabiyot"], teachers[5], 400000),
        ]

        groups = []
        months_names = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]

        payments_to_create = []

        for g_idx, (gname, subj, main_teacher, fee) in enumerate(groups_info):
            grp, _ = Group.objects.get_or_create(
                name=gname,
                defaults={'subject': subj, 'created_at': timezone.now() - timedelta(days=365)}
            )
            grp.teachers.add(main_teacher)

            GroupPaymentInfo.objects.get_or_create(
                group=grp,
                defaults={
                    'course_duration_months': 12,
                    'monthly_fee': fee
                }
            )

            # O'quvchilarni taqsimlash
            assigned = students[g_idx*6 : (g_idx+1)*6 + 2]
            for st in assigned:
                GroupStudentMembership.objects.get_or_create(
                    student=st,
                    group=grp,
                    defaults={'joined_at': timezone.now() - timedelta(days=330)}
                )

                # 12 oylik to'lovlar
                for m_idx, m_name in enumerate(months_names):
                    if (g_idx + m_idx) % 7 != 0:
                        payments_to_create.append(
                            StudentPayment(
                                student=st,
                                group=grp,
                                month=m_name,
                                amount_paid=fee
                            )
                        )
            groups.append(grp)

        StudentPayment.objects.all().delete()
        StudentPayment.objects.bulk_create(payments_to_create, ignore_conflicts=True)
        self.stdout.write(f"{len(groups)} ta guruh va {len(payments_to_create)} ta 1 yillik to'lovlar shakllantirildi.")

        # 7. Dars Jadvallari
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

        # 8. 1 YILLIK DARSLAR VA DAVOMATLAR (BULK)
        start_date = timezone.now().date() - timedelta(days=180)
        end_date = timezone.now().date()

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
                        st_status = 'present' if (st_idx + lesson_num) % 6 != 0 else 'absent'
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

        GroupLesson.objects.bulk_create(lessons_to_create)
        Attendance.objects.bulk_create(attendance_to_create)
        self.stdout.write(f"1 yillik {len(lessons_to_create)} ta dars va {len(attendance_to_create)} ta davomat yozuvi yaratildi.")

        # 9. Quizzes
        for grp in groups:
            teacher = grp.teachers.first()
            quiz, _ = Quiz.objects.get_or_create(
                title=f"{grp.name} - Oraliq Nazorat Quizi",
                group=grp,
                teacher=teacher,
                defaults={'time_limit': 45, 'max_score': 100}
            )

            if not quiz.questions.exists():
                for q_num in range(1, 4):
                    q = Question.objects.create(quiz=quiz, text=f"{grp.subject.name} bo'yicha {q_num}-savol matni?")
                    Answer.objects.create(question=q, text="To'g'ri javob", is_correct=True)
                    Answer.objects.create(question=q, text="Noto'g'ri javob A", is_correct=False)
                    Answer.objects.create(question=q, text="Noto'g'ri javob B", is_correct=False)

            for st in grp.students.all():
                StudentQuizResult.objects.get_or_create(
                    student=st,
                    quiz=quiz,
                    defaults={'score': random.randint(70, 100), 'quiz_last_updated': timezone.now()}
                )

        # 10. DTM Exam
        dtm_exam, _ = DTMExam.objects.get_or_create(
            title="DTM Sinov Imtihoni 2026",
            defaults={
                'registration_deadline': timezone.now() + timedelta(days=10),
                'exam_date': timezone.now() + timedelta(days=15),
                'is_active': True
            }
        )

        for st_idx, st in enumerate(students[:15]):
            reg, _ = DTMRegistration.objects.get_or_create(
                student=st,
                exam=dtm_exam,
                defaults={
                    'block1_subject': 'Matematika',
                    'block2_subject': 'Fizika',
                    'take_compulsory': True,
                    'booklet_number': f"B-10{st_idx+1}"
                }
            )
            StudentDTMExamResult.objects.get_or_create(
                registration=reg,
                defaults={
                    'score_block1': 85.5,
                    'score_block2': 58.2,
                    'score_compulsory': 30.0,
                    'total_score': 173.7
                }
            )

        # 11. SystemAnnouncement
        SystemAnnouncement.objects.get_or_create(
            title="Yangi o'quv yili mashg'ulotlari!",
            defaults={
                'message': "Hurmatli o'quvchilar va o'qituvchilar, dars jadvallari va xonalar biriktirildi.",
                'target_role': 'all',
                'category': 'always_show',
                'end_time': timezone.now() + timedelta(days=30),
                'is_active': True
            }
        )

        self.stdout.write(self.style.SUCCESS("BARCHA MA'LUMOTLAR POSTGRESQL (fumaisak_db) BAZASIGA MUVAFFAQIYATLI YUKLANDI!"))
