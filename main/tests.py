from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum
from main.models import Group, StudentPayment, GroupPaymentInfo, DTMQuestionPool, DTMAnswerPool, StudentQuizResult

CustomUser = get_user_model()

class TizimOptimizationTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create users
        self.admin_user = CustomUser.objects.create_user(
            username='admin_test',
            password='testpassword123',
            role='admin',
            first_name='Admin',
            last_name='Test'
        )
        self.student_user = CustomUser.objects.create_user(
            username='student_test',
            password='testpassword123',
            role='student',
            first_name="O'g'iloy",
            last_name='Toshmatova'
        )
        
        # Create group and payment info
        self.group = Group.objects.create(name="Matematika Guruh 1")
        self.payment_info = GroupPaymentInfo.objects.create(
            group=self.group,
            course_duration_months=3,
            monthly_fee=500000.00
        )
        
        # Create payments
        StudentPayment.objects.create(
            student=self.student_user,
            group=self.group,
            month="Avgust 2026",
            amount_paid=450000.00
        )

    def test_financial_stats_api_optimization(self):
        self.client.login(username='admin_test', password='testpassword123')
        url = reverse('admin_financial_stats_api')
        response = self.client.get(url, {'year': '2026'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check monthly revenue list contains Avgust
        avgust_data = next((item for item in data['monthly_revenue'] if item['month'] == 'Avgust'), None)
        self.assertIsNotNone(avgust_data)
        self.assertEqual(avgust_data['total'], 450000.00)
        
        # Check group payments
        group_data = next((item for item in data['group_payments'] if item['group_name'] == 'Matematika Guruh 1'), None)
        self.assertIsNotNone(group_data)
        self.assertEqual(group_data['total'], 450000.00)

    def test_telegram_webhook_secret_token(self):
        url = reverse('telegram_webhook')
        
        # Without settings configured (bypassed)
        response = self.client.post(url, '{}', content_type='application/json')
        # Bypassed token but empty/invalid json should give status 200 (if handled successfully or json formats successfully)
        self.assertEqual(response.status_code, 200)

        # With secret token configured
        with self.settings(TELEGRAM_WEBHOOK_SECRET_TOKEN='secret12345'):
            # Unauthorized request (missing header)
            response = self.client.post(url, '{}', content_type='application/json')
            self.assertEqual(response.status_code, 403)
            
            # Authorized request (correct header)
            response = self.client.post(
                url, 
                '{}', 
                content_type='application/json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='secret12345'
            )
            self.assertEqual(response.status_code, 200)

    def test_dtm_question_pool_sampling(self):
        # Create pool of questions
        q1 = DTMQuestionPool.objects.create(subject="Ona tili", is_compulsory=True, text="Savol 1")
        DTMAnswerPool.objects.create(question=q1, text="Javob A", is_correct=True)
        DTMAnswerPool.objects.create(question=q1, text="Javob B", is_correct=False)
        
        q2 = DTMQuestionPool.objects.create(subject="Ona tili", is_compulsory=True, text="Savol 2")
        DTMAnswerPool.objects.create(question=q2, text="Javob A", is_correct=True)
        
        # Querying sampled questions
        import random
        
        q_ids = list(DTMQuestionPool.objects.filter(subject="Ona tili", is_compulsory=True).values_list('id', flat=True))
        self.assertEqual(len(q_ids), 2)
        
        sampled_ids = random.sample(q_ids, 1)
        questions = list(DTMQuestionPool.objects.filter(id__in=sampled_ids).prefetch_related('answers'))
        self.assertEqual(len(questions), 1)
        self.assertTrue(len(questions[0].answers.all()) >= 1)

    def test_file_upload_validators(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.exceptions import ValidationError
        from main.validators import validate_image_file, validate_document_file, validate_video_file
        
        # Test valid image
        valid_img = SimpleUploadedFile("avatar.png", b"file_content", content_type="image/png")
        validate_image_file(valid_img)  # Should not raise ValidationError
        
        # Test invalid image extension
        invalid_img = SimpleUploadedFile("avatar.py", b"print('hack')", content_type="text/x-python")
        with self.assertRaises(ValidationError):
            validate_image_file(invalid_img)
            
        # Test invalid image size
        large_img = SimpleUploadedFile("large.png", b"x" * (6 * 1024 * 1024), content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_image_file(large_img)

        # Test valid document
        valid_doc = SimpleUploadedFile("homework.pdf", b"pdf_data", content_type="application/pdf")
        validate_document_file(valid_doc)  # Should not raise

        # Test invalid document extension
        invalid_doc = SimpleUploadedFile("homework.exe", b"exe_data")
        with self.assertRaises(ValidationError):
            validate_document_file(invalid_doc)

    def test_payment_order_and_completion(self):
        from main.models import PaymentOrder, WalletTransaction
        from main.payment_service import complete_payment_order
        
        # 1. Top-up order
        order = PaymentOrder.objects.create(
            student=self.student_user,
            amount=100000.00,
            provider='payme',
            status='waiting'
        )
        self.assertEqual(self.student_user.balance, 0.00)
        
        # Complete payment
        complete_payment_order(order, "TEST_TRANS_12345")
        
        order.refresh_from_db()
        self.student_user.refresh_from_db()
        
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.transaction_id, "TEST_TRANS_12345")
        self.assertEqual(self.student_user.balance, 100000.00)
        
        # Check wallet transaction log
        w_trans = WalletTransaction.objects.filter(student=self.student_user, transaction_type='top_up').first()
        self.assertIsNotNone(w_trans)
        self.assertEqual(w_trans.amount, 100000.00)

