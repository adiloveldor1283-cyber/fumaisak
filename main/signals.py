# main/signals.py

import os
from django.utils import timezone
from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
from django.contrib.sessions.models import Session
from .models import (
    CustomUser, SubjectMaterial, Assignment, AssignmentSubmission,
    GroupLesson, GroupVideo, DTMRegistration, SiteSetting, ProfileSetting, UserSession, DTMQuestionPool,
    GroupStudentMembership, Schedule, Group, DAYS_OF_WEEK
)
from main.utils import run_async

_deleting_group_ids = set()

@receiver(pre_delete, sender=Group)
def mark_group_deleting(sender, instance, **kwargs):
    if instance.pk:
        _deleting_group_ids.add(instance.pk)

@receiver(post_delete, sender=Group)
def clear_group_deleting(sender, instance, **kwargs):
    if instance.pk:
        _deleting_group_ids.discard(instance.pk)

def delete_file_from_storage(file_field):
    """
    Helper function to delete a file from storage if it exists.
    Uses default_storage to work seamlessly with both local and remote (S3) storages.
    """
    if file_field and file_field.name:
        try:
            if default_storage.exists(file_field.name):
                default_storage.delete(file_field.name)
        except Exception as e:
            print(f"Error deleting file {file_field.name}: {str(e)}")

@receiver(pre_save, sender=CustomUser)
def delete_old_profile_image(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_user = CustomUser.objects.get(pk=instance.pk)
    except CustomUser.DoesNotExist:
        return

    old_image = old_user.profile_image
    new_image = instance.profile_image

    if old_image and old_image != new_image:
        delete_file_from_storage(old_image)


@receiver(post_delete, sender=CustomUser)
def delete_profile_image_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.profile_image)


@receiver(post_delete, sender=SubjectMaterial)
def delete_subject_material_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.file)


@receiver(post_delete, sender=Assignment)
def delete_assignment_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.file)


@receiver(post_delete, sender=AssignmentSubmission)
def delete_submission_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.file)


@receiver(post_delete, sender=GroupLesson)
def delete_lesson_file_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.file)


@receiver(post_delete, sender=GroupVideo)
def delete_video_file_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.video_file)


@receiver(post_delete, sender=DTMRegistration)
def delete_dtm_booklet_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.booklet_file)


@receiver(post_delete, sender=SiteSetting)
def delete_sitesetting_image_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)
    from django.core.cache import cache
    cache.delete('site_global_images')
    cache.delete('circular_favicon_png')


@receiver(post_save, sender=SiteSetting)
def clear_sitesetting_cache_on_save(sender, instance, **kwargs):
    from django.core.cache import cache
    cache.delete('site_global_images')
    cache.delete('circular_favicon_png')



@receiver(post_delete, sender=ProfileSetting)
def delete_profilesetting_image_on_delete(sender, instance, **kwargs):
    delete_file_from_storage(instance.image)


@receiver(post_delete, sender=UserSession)
def delete_django_session(sender, instance, **kwargs):
    Session.objects.filter(session_key=instance.session_key).delete()


@receiver(post_delete, sender=DTMQuestionPool)
def delete_dtm_question_image(sender, instance, **kwargs):
    if instance.text:
        import re
        match = re.search(r'\[DIAGRAM_IMAGE:([^\]]+)\]', instance.text)
        if match:
            filename = match.group(1)
            try:
                if default_storage.exists(f"dtm_images/{filename}"):
                    default_storage.delete(f"dtm_images/{filename}")
            except Exception as e:
                print(f"Error deleting DTM image: {e}")


@receiver(post_save, sender=GroupStudentMembership)
def notify_teacher_student_added(sender, instance, created, **kwargs):
    if created:
        student = instance.student
        group = instance.group
        teachers = group.teachers.all()
        for teacher in teachers:
            if teacher.telegram_chat_id:
                msg = (
                    f"<b>Yangi o'quvchi qo'shildi!</b> 👥\n\n"
                    f"Guruh: {group.name}\n"
                    f"O'quvchi: {student.get_full_name()} ({student.phone_number})"
                )
                from main.telegram_service import send_telegram_message
                run_async(send_telegram_message, teacher.telegram_chat_id, msg)


@receiver(post_delete, sender=GroupStudentMembership)
def notify_teacher_student_removed(sender, instance, **kwargs):
    student = instance.student
    group = instance.group
    teachers = group.teachers.all()
    for teacher in teachers:
        if teacher.telegram_chat_id:
            msg = (
                f"<b>O'quvchi guruhdan chiqarildi!</b> 👤❌\n\n"
                f"Guruh: {group.name}\n"
                f"O'quvchi: {student.get_full_name()}"
            )
            from main.telegram_service import send_telegram_message
            run_async(send_telegram_message, teacher.telegram_chat_id, msg)


@receiver(pre_save, sender=Schedule)
def track_old_schedule(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_inst = Schedule.objects.get(pk=instance.pk)
            instance._old_day = old_inst.day
            instance._old_start_time = old_inst.start_time
            instance._old_end_time = old_inst.end_time
        except Schedule.DoesNotExist:
            instance._old_day = None
            instance._old_start_time = None
            instance._old_end_time = None


@receiver(post_save, sender=Schedule)
def notify_schedule_saved(sender, instance, created, **kwargs):
    try:
        group = instance.group
        teacher = instance.teacher
    except Exception:
        return

    day_name = instance.get_day_display()
    start = instance.start_time.strftime('%H:%M')
    end = instance.end_time.strftime('%H:%M')

    if created:
        teacher_msg = (
            f"📅 <b>Yangi dars jadvali biriktirildi!</b> ➕\n\n"
            f"Guruh: <b>{group.name}</b>\n"
            f"Kun: <b>{day_name}</b>\n"
            f"Vaqt: <b>{start} - {end}</b>"
        )
        student_msg = (
            f"📅 <b>Yangi dars jadvali belgilandi!</b> ➕\n\n"
            f"Guruh: <b>{group.name}</b>\n"
            f"O'qituvchi: <b>{teacher.get_full_name()}</b>\n"
            f"Kun: <b>{day_name}</b>\n"
            f"Vaqt: <b>{start} - {end}</b>"
        )
    else:
        old_day = getattr(instance, '_old_day', None)
        old_start = getattr(instance, '_old_start_time', None)
        old_end = getattr(instance, '_old_end_time', None)

        # Agar kun va vaqtlar mutlaqo o'zgarmagan bo'lsa - xabar jo'natmaymiz!
        if old_day == instance.day and old_start == instance.start_time and old_end == instance.end_time:
            return

        day_dict = dict(DAYS_OF_WEEK)
        old_day_name = day_dict.get(old_day, old_day) if old_day else None
        old_start_str = old_start.strftime('%H:%M') if old_start else None
        old_end_str = old_end.strftime('%H:%M') if old_end else None

        lines = [f"Guruh: <b>{group.name}</b>"]
        if old_day and old_day != instance.day:
            lines.append(f"Kun: <b>{old_day_name}</b> ➡️ <b>{day_name}</b>")
        else:
            lines.append(f"Kun: <b>{day_name}</b>")

        if old_start and old_end and (old_start != instance.start_time or old_end != instance.end_time):
            lines.append(f"Yangi vaqt: <b>{start} - {end}</b>\n(Oldingi vaqt: <s>{old_start_str} - {old_end_str}</s>)")
        else:
            lines.append(f"Vaqt: <b>{start} - {end}</b>")

        details_text = "\n".join(lines)

        teacher_msg = (
            f"🔄 <b>Dars jadvali o'zgartirildi!</b> 📅\n\n"
            f"{details_text}"
        )
        student_msg = (
            f"🔄 <b>Dars jadvali o'zgartirildi!</b> 📅\n\n"
            f"O'qituvchi: <b>{teacher.get_full_name()}</b>\n"
            f"{details_text}"
        )

    from main.telegram_service import send_telegram_message

    # 1. O'qituvchiga yuborish
    if teacher and teacher.telegram_chat_id:
        run_async(send_telegram_message, teacher.telegram_chat_id, teacher_msg)

    # 2. Guruh o'quvchilariga yuborish
    memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
    for m in memberships:
        st = m.student
        if st.role == 'student' and st.telegram_chat_id:
            run_async(send_telegram_message, st.telegram_chat_id, student_msg)


@receiver(post_delete, sender=Schedule)
def notify_schedule_deleted(sender, instance, **kwargs):
    # Agar butun guruh o'chirilayotgan bo'lsa (CASCADE), alohida har bir dars uchun xabar jo'natilmaydi
    if instance.group_id in _deleting_group_ids:
        return

    try:
        group = instance.group
        teacher = instance.teacher
    except Exception:
        return

    if not group or not teacher:
        return

    day_name = instance.get_day_display()
    start = instance.start_time.strftime('%H:%M')
    end = instance.end_time.strftime('%H:%M')

    teacher_msg = (
        f"❌ <b>Dars jadvali bekor qilindi!</b> 📅\n\n"
        f"Quyidagi dars jadvali sizdan olib tashlandi:\n"
        f"Guruh: <b>{group.name}</b>\n"
        f"Kun: <b>{day_name}</b>\n"
        f"Vaqt: <b>{start} - {end}</b>"
    )
    student_msg = (
        f"❌ <b>Dars jadvali bekor qilindi!</b> 📅\n\n"
        f"Guruh: <b>{group.name}</b>\n"
        f"Kun: <b>{day_name}</b>\n"
        f"Vaqt: <b>{start} - {end}</b> darsi bekor qilindi."
    )

    from main.telegram_service import send_telegram_message

    # 1. O'qituvchiga yuborish
    if teacher and teacher.telegram_chat_id:
        run_async(send_telegram_message, teacher.telegram_chat_id, teacher_msg)

    # 2. Guruh o'quvchilariga yuborish
    memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
    for m in memberships:
        st = m.student
        if st.role == 'student' and st.telegram_chat_id:
            run_async(send_telegram_message, st.telegram_chat_id, student_msg)


# ==========================================
# 🎓 STUDENT TELEGRAM NOTIFICATION SIGNALS
# ==========================================
from django.db.models.signals import post_save
from main.models import Quiz, Assignment, AssignmentSubmission, GroupStudentMembership

@receiver(post_save, sender=Assignment)
def notify_students_new_assignment(sender, instance, created, **kwargs):
    if created:
        group = instance.group
        subject_name = group.subject.name if group.subject else "Barcha fanlar"
        memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
        
        if instance.deadline:
            if timezone.is_aware(instance.deadline):
                deadline_str = timezone.localtime(instance.deadline).strftime('%d.%m.%Y %H:%M')
            else:
                deadline_str = instance.deadline.strftime('%d.%m.%Y %H:%M')
        else:
            deadline_str = "Belgilanmagan"

        from main.telegram_service import send_telegram_message
        for m in memberships:
            student = m.student
            if student.role == 'student' and student.telegram_chat_id:
                msg = (
                    f"📚 <b>Yangi uy vazifasi yuklandi!</b> 📝\n\n"
                    f"Fan: <b>{subject_name}</b>\n"
                    f"Mavzu: <b>{instance.title}</b>\n"
                    f"Muddat (Deadline): <b>{deadline_str}</b>\n\n"
                    f"🔗 Profilingiz orqali topshiriqni yuklab oling va bajaring."
                )
                run_async(send_telegram_message, student.telegram_chat_id, msg)


@receiver(post_save, sender=Quiz)
def notify_students_new_quiz(sender, instance, created, **kwargs):
    if created:
        group = instance.group
        memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
        
        from main.telegram_service import send_telegram_message
        for m in memberships:
            student = m.student
            if student.role == 'student' and student.telegram_chat_id:
                msg = (
                    f"✏️ <b>Guruhda yangi onlayn test e'lon qilindi!</b> ⏱\n\n"
                    f"Guruh: <b>{group.name}</b>\n"
                    f"Test nomi: <b>{instance.title}</b>\n"
                    f"Vaqt limiti: <b>{instance.time_limit} daqiqa</b>\n"
                    f"Maksimal ball: <b>{instance.max_score} ball</b>\n\n"
                    f"🔗 Testni yechish uchun profil paneli orqali test bo'limiga kiring."
                )
                run_async(send_telegram_message, student.telegram_chat_id, msg)


@receiver(post_save, sender=AssignmentSubmission)
def notify_student_assignment_graded(sender, instance, created, **kwargs):
    # Baholangan (grade bo'sh bo'lmaganda va yangilangan yoki yaratilganda)
    if instance.grade is not None:
        student = instance.student
        if student.telegram_chat_id:
            assignment = instance.assignment
            feedback_text = instance.feedback or "Izoh yo'q"
            from main.telegram_service import send_telegram_message
            msg = (
                f"🔔 <b>Vazifangiz baholandi!</b> 💯\n\n"
                f"Topshiriq: <b>{assignment.title}</b>\n"
                f"Baholangan ball: <b>{instance.grade} / {assignment.max_score}</b>\n"
                f"Izoh (Feedback): <i>{feedback_text}</i>\n\n"
                f"🔗 Profilingiz orqali darslar va vazifalar holatini ko'rishingiz mumkin."
            )
            run_async(send_telegram_message, student.telegram_chat_id, msg)


from django.core.cache import cache

@receiver(post_save, sender=SiteSetting)
@receiver(post_save, sender=ProfileSetting)
@receiver(post_delete, sender=SiteSetting)
@receiver(post_delete, sender=ProfileSetting)
def clear_site_images_cache(sender, instance, **kwargs):
    cache.delete('site_global_images')


from main.models import SystemAnnouncement

@receiver(post_save, sender=SystemAnnouncement)
@receiver(post_delete, sender=SystemAnnouncement)
def clear_announcements_cache(sender, instance, **kwargs):
    for role in ['admin', 'teacher', 'student', 'reception', 'all']:
        cache.delete(f'active_announcements_{role}')






