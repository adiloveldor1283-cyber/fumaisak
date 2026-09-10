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
from django.urls import path, re_path
from django.views.static import serve

from django.conf import settings
from django.conf.urls.static import static
from main import views, teacher, student, adminpanel, payment_views

urlpatterns = [
    path('favicon.ico', views.circular_favicon_view, name='favicon_ico'),
    path('favicon.png', views.circular_favicon_view, name='circular_favicon'),
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),

    # 💳 Online Payments (Payme & Click)
    path('student/payment/create-order/', payment_views.create_payment_order_view, name='create_payment_order'),
    path('student/payment/simulate/<int:order_id>/', payment_views.payment_simulation_view, name='payment_simulation'),
    path('api/payments/payme/', payment_views.payme_webhook_view, name='payme_webhook'),
    path('api/payments/click/', payment_views.click_webhook_view, name='click_webhook'),
    path('api/payments/click/prepare/', payment_views.click_webhook_view, name='click_prepare'),
    path('api/payments/click/complete/', payment_views.click_webhook_view, name='click_complete'),

    path('super-secret-panel-super-juda/', admin.site.urls),
    path('adminpanel/dashboard/', adminpanel.admin_dashboard, name='admin_dashboard'),
    path('adminpanel/all-groups/', adminpanel.all_groups_admin, name='all_groups_admin'),
    path('adminpanel/subjects/', adminpanel.subject_list_admin, name='subject_list_admin'),
    path('adminpanel/subjects/add/', adminpanel.create_subject_admin, name='create_subject_admin'),
    path('adminpanel/subjects/edit/<int:subject_id>/', adminpanel.edit_subject_admin, name='edit_subject_admin'),
    path('adminpanel/subjects/material/delete/<int:material_id>/', adminpanel.delete_subject_material_admin, name='delete_subject_material_admin'),
    path('adminpanel/books-report/', adminpanel.admin_books_report_view, name='admin_books_report'),
    path('adminpanel/salaries/', adminpanel.admin_salaries_view, name='admin_salaries'),
    path('adminpanel/salaries/pay/', adminpanel.admin_pay_teacher_salary, name='admin_pay_teacher_salary'),
    path('adminpanel/salaries/export-csv/', adminpanel.admin_export_salaries_csv, name='admin_export_salaries_csv'),
    path('adminpanel/wallets/', adminpanel.admin_wallets_view, name='admin_wallets'),
    path('adminpanel/wallets/top-up/', adminpanel.admin_top_up_wallet, name='admin_top_up_wallet'),

    path('teacher/teacher_home/', teacher.teacher_home_view, name='teacher_home'),
    path('teacher/subjects/', teacher.teacher_subjects_view, name='teacher_subjects'),
    path('teacher/subjects/material/delete/<int:material_id>/', teacher.delete_subject_material_teacher, name='delete_subject_material_teacher'),
    path('teacher/subjects/book/delete/<int:book_id>/', teacher.delete_book_teacher, name='delete_book_teacher'),
    path('adminpanel/subjects/book/delete/<int:book_id>/', adminpanel.delete_book_admin, name='delete_book_admin'),
    path('student_home/', student.student_home_view, name='student_home'),
    path('student/telegram/disconnect/', student.disconnect_telegram, name='disconnect_telegram'),
    path('student/telegram/generate-otp/', student.generate_telegram_otp_api, name='generate_telegram_otp'),
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

    path('adminpanel/settings/', adminpanel.admin_settings_view, name='admin_settings'),
    path('adminpanel/settings/subadmin/add/', adminpanel.add_subadmin, name='add_subadmin'),
    path('adminpanel/settings/subadmin/edit/<int:subadmin_id>/', adminpanel.edit_subadmin, name='edit_subadmin'),
    path('adminpanel/settings/subadmin/delete/<int:subadmin_id>/', adminpanel.delete_subadmin, name='delete_subadmin'),
    path('adminpanel/sessions/', adminpanel.admin_sessions_view, name='admin_sessions'),
    path('adminpanel/sessions/terminate/<str:session_key>/', adminpanel.terminate_session_view, name='terminate_session'),

    path('adminpanel/admin-password/', adminpanel.admin_password, name='admin_password'),
    path('adminpanel/audit-logs/', adminpanel.admin_audit_logs, name='admin_audit_logs'),
    path('adminpanel/api/financial-stats/', adminpanel.admin_financial_stats_api, name='admin_financial_stats_api'),
    path('adminpanel/api/warning-students/', adminpanel.admin_warning_students_api, name='admin_warning_students_api'),
    path('adminpanel/api/get-discount/<int:group_id>/<int:student_id>/<str:month>/', adminpanel.get_student_discount, name='get_student_discount'),
    path('teacher/api/past-questions/', teacher.teacher_past_questions_api, name='teacher_past_questions_api'),
    path('adminpanel/student-password/<int:student_id>/', adminpanel.reset_student_password, name='student_password'),
    path('adminpanel/teacher-password/<int:teacher_id>/', adminpanel.reset_teacher_password, name='teacher_password'),

    path('students/pdf/', adminpanel.export_students_pdf, name='students_pdf'),
    path('students/excel/', adminpanel.export_students_excel, name='students_excel'),
    path('adminpanel/students/export-excel/', adminpanel.export_students_excel, name='admin_export_students_excel'),

    path('teachers/pdf/', adminpanel.export_teachers_pdf, name='teachers_pdf'),
    path('teachers/excel/', adminpanel.export_teachers_excel, name='teachers_excel'),
    path('adminpanel/teachers/export-excel/', adminpanel.export_teachers_excel, name='admin_export_teachers_excel'),

    path('teacher/groups-list/', teacher.my_groups_view, name='teacher_group_list'),
    path('teacher/groups-list/<int:group_id>/', teacher.group_detail_view, name='group_detail'),
    path('teacher/schedule/', teacher.teacher_schedule_view, name='teacher_schedule'),

    path('adminpanel/edit-schedule/<int:group_id>/', adminpanel.edit_group_teacher_schedule, name='edit_group_teacher_schedule'),
    path('adminpanel/schedules-list/', adminpanel.all_group_schedules_view, name='all_group_schedules'),
    path('adminpanel/schedule-delete/', adminpanel.delete_schedule_view, name='delete_schedule'),
    path('adminpanel/calendar-planner/', adminpanel.admin_calendar_planner, name='admin_calendar_planner'),
    path('adminpanel/api/calendar-schedules/', adminpanel.api_calendar_schedules, name='api_calendar_schedules'),
    path('adminpanel/api/update-schedule-drag/', adminpanel.api_update_schedule_drag, name='api_update_schedule_drag'),
    path('adminpanel/api/delete-schedule/', adminpanel.api_delete_schedule, name='api_delete_schedule'),
    path('adminpanel/api/send-debt-reminder/', adminpanel.send_debt_reminder_api, name='send_debt_reminder_api'),
    path('adminpanel/api/send-telegram-test/', adminpanel.send_telegram_test_api, name='send_telegram_test_api'),

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

    path('teacher/quiz/', teacher.create_quiz, name='create_quiz'),
    path('teacher/quiz/create/<int:group_id>/', teacher.add_questions, name='add_questions'),
    path('teacher/quiz/detail/<int:quiz_id>/', teacher.quiz_detail, name='quiz_detail'),
    path('teacher/quiz/results/<int:quiz_id>/', teacher.teacher_view_results, name='quiz_results'),

    path('student/quizzes/', student.student_quiz_list, name='student_quiz_list'),
    path('quiz/<int:quiz_id>/start/', student.start_quiz, name='start_quiz'),
    path('quiz/<int:quiz_id>/submit/', student.submit_quiz, name='submit_quiz'),

    path('assignments/', student.student_assignments_view, name='student_assignments'),
    path('student/assignments/<int:assignment_id>/submit/', student.submit_assignment, name='submit_assignment'),

    path('teacher/deadline/', teacher.teacher_deadline, name='teacher_deadline'),
    path('teacher/edit_deadline/<int:assignment_id>/', teacher.edit_assignment, name='edit_assignment'),

    path('teacher/attendance-groups/', teacher.teacher_attendance_groups, name='teacher_attendance_groups'),
    path('teacher/attendance-submit/<int:group_id>/', teacher.submit_attendance, name='submit_attendance'),
    path('teacher/attendance/check-class/<int:group_id>/', teacher.teacher_check_class_ajax, name='teacher_check_class_ajax'),
    path('teacher/attendance-groups/<int:group_id>/', teacher.teacher_group_attendance, name='teacher_group_attendance'),

    path('teacher/deadline/<int:assignment_id>/', teacher.teacher_assignment_submissions, name='teacher_assignment_submissions'),
    path('teacher/assignment/grade/', teacher.grade_assignment, name='grade_assignment'),
    path('teacher/quick-grade/', teacher.quick_grade_view, name='quick_grade'),

    path('teacher/groups-list/<int:group_id>/attendance/export/excel/', teacher.export_attendance_excel, name='export_attendance_excel'),
    path('teacher/groups-list/<int:group_id>/grades/export/excel/', teacher.export_grades_excel, name='export_grades_excel'),
    path('teacher/groups-list/<int:group_id>/grades/export/pdf/', teacher.export_grades_pdf, name='export_grades_pdf'),


    path('student_groups_view/', student.student_groups_view, name='student_groups_view'),
    path('student/subjects/', student.student_subjects_view, name='student_subjects_view'),
    path('student/books/<int:book_id>/flipbook/', student.student_book_flipbook_view, name='student_book_flipbook'),
    path('student_profile/', student.student_profile_view, name='student_profile'),
    path('student_schedule/', student.student_schedule_view, name='student_schedule'),


    path('adminpanel/import-students/', adminpanel.import_students_csv, name='import_students_csv'),
    path('groups/<int:group_id>/payment/add/', adminpanel.add_group_payment, name='add_group_payment'),

    path('adminpanel/group-payment/', adminpanel.group_payment_list, name='group_payment_list'),
    path('adminpanel/all-payments/', adminpanel.admin_all_payments, name='admin_all_payments'),
    path('admin/student/<int:student_id>/payments/pdf/', adminpanel.student_payment_pdf, name='student_payment_pdf'),

    path("groups/<int:group_id>/students/", adminpanel.group_students, name="group_students"),
    path("groups/<int:group_id>/students/<int:student_id>/payment/", adminpanel.student_payment, name="student_payment"),

    path("students/", adminpanel.student_list, name="student_list"),
    path("students/<int:student_id>/payments/", adminpanel.student_payment_history, name="student_payment_history"),
    path('payment/<int:payment_id>/receipt/', adminpanel.payment_receipt, name='payment_receipt'),
    path('payment/verify/<int:payment_id>/<str:code>/', adminpanel.verify_payment, name='verify_payment'),

    path('student_payment/', student.student_payment_view, name='student_payment_view'),

    # AI Quiz URLs
    path('student/ai-quiz/', student.ai_quiz_dashboard, name='ai_quiz_dashboard'),
    path('student/ai-quiz/<int:quiz_id>/', student.ai_quiz_take, name='ai_quiz_take'),
    path('student/ai-quiz/<int:quiz_id>/submit/', student.ai_quiz_submit, name='ai_quiz_submit'),
    path('student/ai-quiz/<int:quiz_id>/results/', student.ai_quiz_results, name='ai_quiz_results'),
    path('student/ai-plan/', student.student_ai_plan, name='student_ai_plan'),
    path('student/groups/<int:group_id>/', student.student_group_detail, name='student_group_detail'),

    # Announcements
    path('adminpanel/announcements/', adminpanel.announcement_list, name='announcement_list'),
    path('adminpanel/announcements/create/', adminpanel.create_announcement, name='create_announcement'),
    path('adminpanel/announcements/edit/<int:announcement_id>/', adminpanel.edit_announcement, name='edit_announcement'),
    path('adminpanel/announcements/delete/<int:announcement_id>/', adminpanel.delete_announcement, name='delete_announcement'),
    path('announcements/dismiss/<int:announcement_id>/', views.dismiss_announcement, name='dismiss_announcement'),

    # Debtors and CSV exports
    path('adminpanel/debtors/', adminpanel.debtors_list, name='debtors_list'),
    path('adminpanel/debtors/export/', adminpanel.export_debtors_csv, name='export_debtors_csv'),
    path('adminpanel/payments/export/', adminpanel.export_payments_csv, name='export_payments_csv'),

    # Admin Attendance Management
    path('adminpanel/attendance/', adminpanel.admin_attendance_overview, name='admin_attendance_overview'),
    path('adminpanel/attendance/group/<int:group_id>/', adminpanel.admin_group_attendance, name='admin_group_attendance'),
    path('adminpanel/attendance/update-ajax/', adminpanel.admin_update_attendance_ajax, name='admin_update_attendance_ajax'),

    # Video/Media routes
    path('teacher/media/', teacher.teacher_media_gallery, name='teacher_media_gallery'),
    path('teacher/media/delete/<int:video_id>/', teacher.teacher_delete_video, name='teacher_delete_video'),
    path('teacher/media/edit/<int:video_id>/', teacher.teacher_edit_video, name='teacher_edit_video'),

    path('student/media/', student.student_media_gallery, name='student_media_gallery'),

    path('adminpanel/media/', adminpanel.admin_media_gallery, name='admin_media_gallery'),
    path('adminpanel/media/delete/<int:video_id>/', adminpanel.admin_delete_video, name='admin_delete_video'),
    path('adminpanel/media/edit/<int:video_id>/', adminpanel.admin_edit_video, name='admin_edit_video'),

    path('adminpanel/quiz/results/<int:quiz_id>/', adminpanel.admin_quiz_results, name='admin_quiz_results'),
    path('adminpanel/assignments/<int:assignment_id>/submissions/', adminpanel.admin_assignment_submissions, name='admin_assignment_submissions'),
    path('adminpanel/assignments/grade/', adminpanel.admin_grade_assignment, name='admin_grade_assignment'),

    # DTM Mock Exam & OMR URLs
    path('adminpanel/dtm/', adminpanel.admin_dtm_list, name='admin_dtm_list'),
    path('adminpanel/dtm/create/', adminpanel.admin_dtm_create, name='admin_dtm_create'),
    path('adminpanel/dtm/edit/<int:exam_id>/', adminpanel.admin_dtm_edit, name='admin_dtm_edit'),
    path('adminpanel/dtm/upload/', adminpanel.admin_dtm_manual_bulk_add, name='admin_dtm_upload_ai'),
    path('adminpanel/dtm/<int:exam_id>/registrations/', adminpanel.admin_dtm_registrations, name='admin_dtm_registrations'),
    path('adminpanel/dtm/generate-booklet/<int:registration_id>/', adminpanel.admin_dtm_generate_booklet, name='admin_dtm_generate_booklet'),
    path('adminpanel/dtm/omr-scan/', adminpanel.admin_dtm_omr_scan, name='admin_dtm_omr_scan'),
    path('adminpanel/dtm/<int:exam_id>/results/', adminpanel.admin_dtm_results_view, name='admin_dtm_results_view'),
    path('adminpanel/dtm/bubble-sheet/', adminpanel.dtm_bubble_sheet_pdf, name='dtm_bubble_sheet_pdf'),
    path('adminpanel/dtm/questions/', adminpanel.admin_dtm_questions_list, name='admin_dtm_questions_list'),
    path('adminpanel/dtm/questions/edit/<int:question_id>/', adminpanel.admin_dtm_question_edit, name='admin_dtm_question_edit'),
    path('adminpanel/dtm/questions/delete/<int:question_id>/', adminpanel.admin_dtm_question_delete, name='admin_dtm_question_delete'),
    path('adminpanel/dtm/questions/add/', adminpanel.admin_dtm_question_add, name='admin_dtm_question_add'),
    path('adminpanel/dtm/api/ai-parse/', adminpanel.admin_dtm_ai_auto_parse_api, name='admin_dtm_ai_auto_parse_api'),
    path('adminpanel/dtm/api/format-formula/', adminpanel.admin_dtm_format_formula_api, name='admin_dtm_format_formula_api'),

    path('student/dtm/', student.student_dtm_list, name='student_dtm_list'),
    path('student/dtm/register/<int:exam_id>/', student.student_dtm_register, name='student_dtm_register'),

    # System Error logs and Locked pages
    path('adminpanel/error-logs/', adminpanel.admin_error_logs, name='admin_error_logs'),
    path('adminpanel/error-logs/resolve/<int:log_id>/', adminpanel.admin_resolve_error, name='admin_resolve_error'),
    path('adminpanel/locked-pages/', adminpanel.admin_locked_pages, name='admin_locked_pages'),
    path('adminpanel/locked-pages/unlock/<int:page_id>/', adminpanel.admin_unlock_page, name='admin_unlock_page'),
]

# 🖼️ MEDIA FAYLLARNI HAR QANDAY REJIMDA (DEBUG=True / DEBUG=False / Railway Volume) UZATISH:
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

