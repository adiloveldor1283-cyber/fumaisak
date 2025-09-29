"""
URL configuration for DjangoProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static
from main import views, teacher, student, adminpanel

urlpatterns = [
    path('', views.login_view, name='login'),
    path('super-secret-panel-super-juda/', admin.site.urls),
    path('adminpanel/all-groups/', adminpanel.all_groups_admin, name='all_groups_admin'),

    path('teacher/teacher_home/', teacher.teacher_home_view, name='teacher_home'),
    path('student_home/', student.student_home_view, name='student_home'),
    path('teacher_profile/', teacher.teacher_profile_view, name='teacher_profile'),
    path('teacher/students_list/', teacher.my_student_view, name='teacher_students_list'),
    path('adminpanel/edit-group/<int:group_id>/', adminpanel.edit_group_admin, name='edit_group_admin'),
    path('adminpanel/add-group/', adminpanel.create_group_admin, name='create_group_admin'),

    path('adminpanel/students-list/', adminpanel.students_list_admin, name='students_list_admin'),
    path('adminpanel/add-student/', adminpanel.add_student, name='add_student'),
    path('adminpanel/edit-student/<int:student_id>/', adminpanel.edit_student, name='edit_student'),

    path('adminpanel/teachers-list/', adminpanel.teachers_list_admin, name='teachers_list_admin'),
    path('adminpanel/edit-teacher/<int:teacher_id>/', adminpanel.edit_teacher, name='edit_teacher'),
    path('adminpanel/add-teacher/', adminpanel.add_teacher, name='add_teacher'),

    path('adminpanel/admin-password/', adminpanel.admin_password, name='admin_password'),
    path('adminpanel/student-password/<int:student_id>/', adminpanel.reset_student_password, name='student_password'),
    path('adminpanel/teacher-password/<int:teacher_id>/', adminpanel.reset_teacher_password, name='teacher_password'),

    path('students/pdf/', adminpanel.export_students_pdf, name='students_pdf'),

    path('teacher/groups-list/', teacher.my_groups_view, name='teacher_group_list'),
    path('teacher/group-detail/<int:group_id>/', teacher.group_detail_view, name='group_detail'),
    path('teacher/schedule/', teacher.teacher_schedule_view, name='teacher_schedule'),

    path('adminpanel/edit-schedule/<int:group_id>/', adminpanel.edit_group_teacher_schedule, name='edit_group_teacher_schedule'),
    path('adminpanel/schedules-list/', adminpanel.all_group_schedules_view, name='all_group_schedules'),
    path('adminpanel/schedule-delete/', adminpanel.delete_schedule_view, name='delete_schedule'),

    path('adminpanel/add-assignments/', adminpanel.add_topshiriq, name='add_topshiriq'),
    path('adminpanel/assignments-list/', adminpanel.admin_assignment_list, name='admin_assignment_list'),
    path('adminpanel/edit-assignments/<int:assignment_id>/', adminpanel.edit_topshiriq, name='edit_topshiriq'),

    path('adminpanel/delete-assignments/<int:assignment_id>/', adminpanel.admin_delete_assignment, name='admin_delete_assignment'),

    path('adminpanel/add-quiz/', adminpanel.add_quiz, name='add_quiz'),
    path('adminpanel/quizs-list/', adminpanel.quiz_list, name='quiz_list'),
    path('adminpanel/edit-quiz/<int:quiz_id>/', adminpanel.edit_quiz, name='edit_quiz'),
    path('adminpanel/quiz-delete/<int:quiz_id>/', adminpanel.delete_quiz, name='delete_quiz'),

    path('adminpanel/add-questions/', adminpanel.add_test_admin, name='add_test_admin'),
    path('adminpanel/questions-list/', adminpanel.question_list, name='question_list'),
    path('adminpanel/edit-questions/<int:question_id>/', adminpanel.update_question, name='update_question'),
    path('adminpanel/<int:pk>/questions-delete/', adminpanel.delete_question, name='delete_question'),

    path('teacher/create-test/', teacher.create_quiz, name='create_quiz'),
    path('teacher/add-test/<int:group_id>/', teacher.add_questions, name='add_questions'),
    path('teacher/detail-test/<int:quiz_id>/', teacher.quiz_detail, name='quiz_detail'),
    path('teacher/test-results/<int:quiz_id>/', teacher.teacher_view_results, name='quiz_results'),

    path('student/quizzes/', student.student_quiz_list, name='student_quiz_list'),
    path('quiz/<int:quiz_id>/start/', student.start_quiz, name='start_quiz'),
    path('quiz/<int:quiz_id>/submit/', student.submit_quiz, name='submit_quiz'),

    path('assignments/', student.student_assignments_view, name='student_assignments'),
    path('student/assignments/<int:assignment_id>/submit/', student.submit_assignment, name='submit_assignment'),

    path('teacher/deadline/', teacher.teacher_deadline, name='teacher_deadline'),
    path('teacher/deadline/<int:assignment_id>/', teacher.edit_assignment, name='edit_assignment'),

    path('teacher/attendance-groups/', teacher.teacher_attendance_groups, name='teacher_attendance_groups'),
    path('teacher/attendance-submit/<int:group_id>/', teacher.submit_attendance, name='submit_attendance'),
    path('teacher/attendance-list/<int:group_id>/', teacher.teacher_group_attendance, name='teacher_group_attendance'),

    path('teacher/assignment/<int:assignment_id>/', teacher.teacher_assignment_submissions, name='teacher_assignment_submissions'),
    path('teacher/assignment/grade/', teacher.grade_assignment, name='grade_assignment'),


    path('student_groups_view/', student.student_groups_view, name='student_groups_view'),
    path('student_profile/', student.student_profile_view, name='student_profile'),
    path('student_schedule/', student.student_schedule_view, name='student_schedule'),


    path('adminpanel/import-students/', adminpanel.import_students_csv, name='import_students_csv'),
    path('groups/<int:group_id>/payment/add/', adminpanel.add_group_payment, name='add_group_payment'),

    path('adminpanel/group-payment/', adminpanel.group_payment_list, name='group_payment_list'),
    path('admin/student/<int:student_id>/payments/pdf/', adminpanel.student_payment_pdf, name='student_payment_pdf'),

    path("groups/<int:group_id>/students/", adminpanel.group_students, name="group_students"),
    path("groups/<int:group_id>/students/<int:student_id>/payment/", adminpanel.student_payment, name="student_payment"),

    path("students/", adminpanel.student_list, name="student_list"),
    path("students/<int:student_id>/payments/", adminpanel.student_payment_history, name="student_payment_history"),
    path('payment/<int:payment_id>/receipt/', adminpanel.payment_receipt, name='payment_receipt'),
    path('payment/verify/<int:payment_id>/<str:code>/', adminpanel.verify_payment, name='verify_payment'),

    path('student_payment/', student.student_payment_view, name='student_payment_view'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
