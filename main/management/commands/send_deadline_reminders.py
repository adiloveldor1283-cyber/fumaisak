import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import Assignment, AssignmentSubmission, GroupStudentMembership
from main.telegram_service import send_telegram_message

class Command(BaseCommand):
    help = 'Sends Telegram reminders to students 24 hours before assignment deadline'

    def handle(self, *args, **options):
        self.stdout.write("Checking assignment deadlines...")
        now = timezone.now()
        
        # 23 va 24 soat oralig'idagi muddatlarni tekshiramiz
        remind_start = now + datetime.timedelta(hours=23)
        remind_end = now + datetime.timedelta(hours=24)
        
        assignments = Assignment.objects.filter(deadline__range=(remind_start, remind_end)).select_related('group', 'group__subject')
        
        if not assignments.exists():
            self.stdout.write(self.style.SUCCESS("No assignments deadline in the next 23-24 hours."))
            return

        for assignment in assignments:
            group = assignment.group
            subject_name = group.subject.name if group.subject else "Barcha fanlar"
            
            # Guruhdagi barcha faol o'quvchilar
            memberships = GroupStudentMembership.objects.filter(group=group).select_related('student')
            
            # Avvalroq topshirib bo'lgan o'quvchilar IDs
            submitted_ids = set(AssignmentSubmission.objects.filter(assignment=assignment).values_list('student_id', flat=True))
            
            count = 0
            for m in memberships:
                student = m.student
                if student.role == 'student' and student.id not in submitted_ids and student.telegram_chat_id:
                    deadline_str = timezone.localtime(assignment.deadline).strftime('%d.%m.%Y %H:%M') if timezone.is_aware(assignment.deadline) else assignment.deadline.strftime('%d.%m.%Y %H:%M')
                    msg = (
                        f"⚠️ <b>Topshiriq muddati yaqinlashmoqda!</b> ⏳\n\n"
                        f"📚 Fan: <b>{subject_name}</b>\n"
                        f"📝 Vazifa: <b>{assignment.title}</b>\n"
                        f"📅 Muddat (Deadline): <b>{deadline_str}</b> (taxminan 24 soat qoldi!)\n\n"
                        f"🔗 Iltimos, topshiriqni o'z vaqtida shaxsiy kabinetingiz orqali yuklang."
                    )
                    success = send_telegram_message(student.telegram_chat_id, msg)
                    if success:
                        count += 1
            
            self.stdout.write(self.style.SUCCESS(f"Sent {count} reminders for assignment: '{assignment.title}' (Group: {group.name})"))
