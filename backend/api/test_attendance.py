from datetime import datetime, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AttendanceAttempt, AttendanceRecord, AttendanceSession, Profile, TrainingCamp


class AttendanceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.camp = TrainingCamp.get_active()
        if not self.camp:
            self.camp = TrainingCamp.objects.create(
                name='Attendance camp',
                slug='attendance-camp',
                start_date='2026-07-01',
                end_date='2026-07-31',
                is_active=True,
            )
        self.student = User.objects.create_user(username='attendance-student', password='Student12345')
        self.other_student = User.objects.create_user(username='attendance-other', password='Student12345')
        self.admin = User.objects.create_user(username='attendance-admin', password='Admin12345', is_staff=True)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])
        self.other_admin = User.objects.create_user(username='attendance-admin-2', password='Admin12345')
        self.other_admin.profile.role = Profile.Role.ADMIN
        self.other_admin.profile.save(update_fields=['role'])

    @staticmethod
    def local_datetime(hour, minute=0):
        return timezone.make_aware(
            datetime(2026, 7, 15, hour, minute),
            timezone.get_current_timezone(),
        )

    def generate_morning_session(self, code='1234'):
        return AttendanceSession.objects.create(
            camp=self.camp,
            date=self.local_datetime(9).date(),
            time_slot=AttendanceSession.TimeSlot.MORNING,
            code=code,
            created_by=self.admin,
        )

    def test_time_slot_boundaries_are_half_open(self):
        self.assertIsNone(AttendanceSession.slot_for_time(time(7, 59)))
        self.assertEqual(AttendanceSession.slot_for_time(time(8, 0)), AttendanceSession.TimeSlot.MORNING)
        self.assertEqual(AttendanceSession.slot_for_time(time(11, 59)), AttendanceSession.TimeSlot.MORNING)
        self.assertEqual(AttendanceSession.slot_for_time(time(12, 0)), AttendanceSession.TimeSlot.AFTERNOON)
        self.assertEqual(AttendanceSession.slot_for_time(time(18, 0)), AttendanceSession.TimeSlot.EVENING)
        self.assertIsNone(AttendanceSession.slot_for_time(time(21, 0)))

    @patch('api.views.attendance_now')
    def test_only_one_admin_can_generate_a_slot_and_other_admin_can_view_code(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.client.force_authenticate(self.admin)
        created_response = self.client.post('/api/attendance/admin/generate/', {}, format='json')

        self.assertEqual(created_response.status_code, 201)
        self.assertRegex(created_response.data['code'], r'^\d{4}$')
        self.assertEqual(AttendanceSession.objects.count(), 1)

        self.client.force_authenticate(self.other_admin)
        duplicate_response = self.client.post('/api/attendance/admin/generate/', {}, format='json')
        overview_response = self.client.get('/api/attendance/admin/overview/?date=2026-07-15')

        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(AttendanceSession.objects.count(), 1)
        morning = next(item for item in overview_response.data['slots'] if item['slot'] == 'morning')
        self.assertEqual(morning['code'], created_response.data['code'])
        self.assertTrue(morning['generated'])

    @patch('api.views.attendance_now')
    def test_student_payload_never_exposes_attendance_code(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.generate_morning_session('5432')
        self.client.force_authenticate(self.student)

        response = self.client.get('/api/attendance/today/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('code', response.data)
        for slot in response.data['slots']:
            self.assertNotIn('code', slot)
        morning = next(item for item in response.data['slots'] if item['slot'] == 'morning')
        self.assertTrue(morning['available'])
        self.assertFalse(morning['signed'])

    @patch('api.views.attendance_now')
    def test_student_can_sign_once_with_current_code(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9, 30)
        session = self.generate_morning_session('1234')
        self.client.force_authenticate(self.student)

        first_response = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')
        second_response = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(AttendanceRecord.objects.filter(session=session, student=self.student).count(), 1)

    @patch('api.views.attendance_now')
    def test_wrong_code_is_rejected(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.generate_morning_session('1234')
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/attendance/check-in/', {'code': '9999'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.filter(student=self.student).exists())

    @patch('api.views.attendance_now')
    def test_five_digit_code_is_rejected(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.generate_morning_session('1234')
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/attendance/check-in/', {'code': '12345'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(AttendanceAttempt.objects.filter(student=self.student).exists())

    @patch('api.views.attendance_now')
    def test_student_is_locked_after_five_wrong_codes(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        session = self.generate_morning_session('1234')
        self.client.force_authenticate(self.student)

        responses = [
            self.client.post('/api/attendance/check-in/', {'code': '9999'}, format='json')
            for _ in range(5)
        ]
        correct_response = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')

        self.assertEqual([response.status_code for response in responses], [400, 400, 400, 400, 429])
        self.assertEqual(correct_response.status_code, 429)
        attempt = AttendanceAttempt.objects.get(session=session, student=self.student)
        self.assertEqual(attempt.failed_attempts, 5)
        self.assertIsNotNone(attempt.locked_at)
        self.assertFalse(AttendanceRecord.objects.filter(session=session, student=self.student).exists())

    @patch('api.views.attendance_now')
    def test_expired_session_cannot_be_signed_or_generated(self, mocked_now):
        self.generate_morning_session('1234')
        mocked_now.return_value = self.local_datetime(21)
        self.client.force_authenticate(self.student)
        sign_response = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')

        self.client.force_authenticate(self.admin)
        generate_response = self.client.post('/api/attendance/admin/generate/', {}, format='json')

        self.assertEqual(sign_response.status_code, 400)
        self.assertEqual(generate_response.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.filter(student=self.student).exists())

    @patch('api.views.attendance_now')
    def test_admin_overview_contains_signed_and_absent_students(self, mocked_now):
        mocked_now.return_value = self.local_datetime(10)
        session = self.generate_morning_session('1234')
        AttendanceRecord.objects.create(session=session, student=self.student)
        self.client.force_authenticate(self.admin)

        response = self.client.get('/api/attendance/admin/overview/?date=2026-07-15')

        self.assertEqual(response.status_code, 200)
        morning = next(item for item in response.data['slots'] if item['slot'] == 'morning')
        self.assertEqual(morning['signed_count'], 1)
        self.assertEqual(morning['records'][0]['username'], self.student.username)
        self.assertIn(self.other_student.username, [item['username'] for item in morning['absent_students']])

    @patch('api.views.attendance_now')
    def test_student_and_admin_permissions_are_separated(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.client.force_authenticate(self.student)
        admin_overview = self.client.get('/api/attendance/admin/overview/')
        admin_generate = self.client.post('/api/attendance/admin/generate/', {}, format='json')

        self.client.force_authenticate(self.admin)
        student_today = self.client.get('/api/attendance/today/')
        student_sign = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')

        self.assertEqual(admin_overview.status_code, 403)
        self.assertEqual(admin_generate.status_code, 403)
        self.assertEqual(student_today.status_code, 403)
        self.assertEqual(student_sign.status_code, 403)
