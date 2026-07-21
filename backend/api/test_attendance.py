from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    AttendanceAttempt,
    AttendanceAuditLog,
    AttendanceRecord,
    AttendanceSession,
    Profile,
    TrainingCamp,
    TrainingCampMembership,
)


class AttendanceApiTests(TestCase):
    def setUp(self):
        cache.clear()
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
        else:
            self.camp.start_date = '2026-07-01'
            self.camp.end_date = '2026-07-31'
            self.camp.is_active = True
            self.camp.save(update_fields=['start_date', 'end_date', 'is_active', 'updated_at'])
        self.student = User.objects.create_user(username='attendance-student', password='Student12345')
        self.other_student = User.objects.create_user(username='attendance-other', password='Student12345')
        self.admin = User.objects.create_user(username='attendance-admin', password='Admin12345', is_staff=True)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])
        self.other_admin = User.objects.create_user(username='attendance-admin-2', password='Admin12345')
        self.other_admin.profile.role = Profile.Role.ADMIN
        self.other_admin.profile.save(update_fields=['role'])
        TrainingCampMembership.objects.bulk_create([
            TrainingCampMembership(camp=self.camp, student=self.student),
            TrainingCampMembership(camp=self.camp, student=self.other_student),
        ])

    @staticmethod
    def local_datetime(hour, minute=0):
        return timezone.make_aware(
            datetime(2026, 7, 15, hour, minute),
            timezone.get_current_timezone(),
        )

    def generate_morning_session(self, code='1234', *, camp=None, session_date=None):
        return AttendanceSession.objects.create(
            camp=camp or self.camp,
            date=session_date or self.local_datetime(9).date(),
            time_slot=AttendanceSession.TimeSlot.MORNING,
            code=code,
            created_by=self.admin,
        )

    def post_makeup(self, session, student=None, reason='学员设备故障，现场确认到场'):
        return self.client.post(
            '/api/attendance/admin/makeups/',
            {
                'session_id': session.id,
                'student_id': (student or self.student).id,
                'reason': reason,
            },
            format='json',
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

    @patch('api.views.attendance_now')
    def test_makeup_requires_strict_application_admin_role(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()

        anonymous_response = self.post_makeup(session)

        self.client.force_authenticate(self.student)
        student_response = self.post_makeup(session)

        staff_student = User.objects.create_user(
            username='attendance-misconfigured-staff',
            password='Pass12345!',
            is_staff=True,
        )
        staff_student.profile.role = Profile.Role.STUDENT
        staff_student.profile.save(update_fields=['role'])
        self.client.force_authenticate(staff_student)
        staff_response = self.post_makeup(session)

        inactive_admin = User.objects.create_user(
            username='attendance-inactive-admin',
            password='Pass12345!',
            is_active=False,
        )
        inactive_admin.profile.role = Profile.Role.ADMIN
        inactive_admin.profile.save(update_fields=['role'])
        self.client.force_authenticate(inactive_admin)
        inactive_admin_response = self.post_makeup(session)

        self.client.force_authenticate(self.other_admin)
        admin_response = self.post_makeup(session)

        self.assertEqual(anonymous_response.status_code, 401)
        self.assertEqual(student_response.status_code, 403)
        self.assertEqual(staff_response.status_code, 403)
        self.assertEqual(inactive_admin_response.status_code, 403)
        self.assertEqual(admin_response.status_code, 201)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    @patch('api.views.attendance_now')
    def test_admin_makeup_records_source_actor_reason_and_audit_snapshot(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13, 15)
        session = self.generate_morning_session()
        self.client.force_authenticate(self.other_admin)

        response = self.post_makeup(
            session,
            reason='  学员设备故障，现场确认到场  ',
        )

        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(session=session, student=self.student)
        self.assertEqual(record.source, AttendanceRecord.Source.ADMIN_MAKEUP)
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertEqual(record.recorded_by, self.other_admin)
        self.assertEqual(record.makeup_reason, '学员设备故障，现场确认到场')
        self.assertEqual(record.signed_at, mocked_now.return_value)
        audit = AttendanceAuditLog.objects.get(record=record)
        self.assertEqual(audit.action, AttendanceAuditLog.Action.GRANT)
        self.assertEqual(audit.actor, self.other_admin)
        self.assertEqual(audit.actor_username, self.other_admin.username)
        self.assertEqual(audit.student_username, self.student.username)
        self.assertEqual(audit.camp_id_snapshot, self.camp.id)
        self.assertEqual(audit.session_date, session.date)

    @patch('api.views.attendance_now')
    def test_makeup_rejects_unknown_fields_and_invalid_reasons(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        self.client.force_authenticate(self.admin)

        spoofed_response = self.client.post(
            '/api/attendance/admin/makeups/',
            {
                'session_id': session.id,
                'student_id': self.student.id,
                'reason': '学员现场确认已经到场',
                'recorded_by': self.student.id,
                'source': 'code',
                'signed_at': '2026-07-15T09:00:00+08:00',
            },
            format='json',
        )
        invalid_responses = [
            self.post_makeup(session, reason=''),
            self.post_makeup(session, reason='原因太短'),
            self.post_makeup(session, reason='a' * 201),
        ]

        self.assertEqual(spoofed_response.status_code, 400)
        self.assertEqual([item.status_code for item in invalid_responses], [400, 400, 400])
        self.assertFalse(AttendanceRecord.objects.filter(session=session).exists())
        self.assertFalse(AttendanceAuditLog.objects.exists())

    @patch('api.views.attendance_now')
    def test_makeup_and_revoke_reject_json_arrays_without_server_error(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        record = AttendanceRecord.objects.create(
            session=session,
            student=self.student,
            source=AttendanceRecord.Source.ADMIN_MAKEUP,
            recorded_by=self.admin,
            makeup_reason='管理员现场确认学员已经到场',
        )
        self.client.force_authenticate(self.admin)

        makeup_response = self.client.post(
            '/api/attendance/admin/makeups/',
            [],
            format='json',
        )
        revoke_response = self.client.post(
            f'/api/attendance/admin/makeups/{record.id}/revoke/',
            [],
            format='json',
        )

        self.assertEqual(makeup_response.status_code, 400)
        self.assertEqual(revoke_response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertFalse(AttendanceAuditLog.objects.exists())

    @patch('api.views.attendance_now')
    def test_makeup_rejects_current_future_and_other_camp_sessions(self, mocked_now):
        self.client.force_authenticate(self.admin)

        current_session = self.generate_morning_session('1201')
        mocked_now.return_value = self.local_datetime(9)
        current_response = self.post_makeup(current_session)

        future_session = self.generate_morning_session(
            '1202',
            session_date=self.local_datetime(9).date() + timedelta(days=1),
        )
        mocked_now.return_value = self.local_datetime(13)
        future_response = self.post_makeup(future_session)

        old_camp = TrainingCamp.objects.create(
            name='Old attendance camp',
            slug='old-attendance-camp',
            start_date='2026-07-01',
            end_date='2026-07-31',
            is_active=False,
        )
        old_session = self.generate_morning_session('1203', camp=old_camp)
        old_camp_response = self.post_makeup(old_session)

        self.assertEqual(current_response.status_code, 400)
        self.assertEqual(future_response.status_code, 400)
        self.assertEqual(old_camp_response.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.exists())

    @patch('api.views.attendance_now')
    def test_makeup_target_must_be_current_active_non_staff_student_member(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        self.client.force_authenticate(self.admin)

        outsider = User.objects.create_user(username='attendance-outsider', password='Pass12345!')
        inactive = User.objects.create_user(username='attendance-inactive', password='Pass12345!', is_active=False)
        TrainingCampMembership.objects.create(camp=self.camp, student=inactive)
        staff_target = User.objects.create_user(
            username='attendance-staff-target',
            password='Pass12345!',
            is_staff=True,
        )
        staff_target.profile.role = Profile.Role.STUDENT
        staff_target.profile.save(update_fields=['role'])
        TrainingCampMembership.objects.create(camp=self.camp, student=staff_target)

        responses = [
            self.post_makeup(session, student=outsider),
            self.post_makeup(session, student=inactive),
            self.post_makeup(session, student=staff_target),
            self.post_makeup(session, student=self.admin),
        ]

        self.assertEqual([item.status_code for item in responses], [400, 400, 400, 400])
        self.assertFalse(AttendanceRecord.objects.exists())

    @patch('api.views.attendance_now')
    def test_normal_or_existing_makeup_cannot_be_duplicated(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        AttendanceRecord.objects.create(session=session, student=self.student)
        self.client.force_authenticate(self.admin)

        normal_duplicate = self.post_makeup(session)
        first_makeup = self.post_makeup(session, student=self.other_student)
        duplicate_makeup = self.post_makeup(session, student=self.other_student)

        self.assertEqual(normal_duplicate.status_code, 409)
        self.assertEqual(first_makeup.status_code, 201)
        self.assertEqual(duplicate_makeup.status_code, 409)
        self.assertEqual(AttendanceRecord.objects.filter(session=session).count(), 2)
        self.assertEqual(AttendanceAuditLog.objects.count(), 1)

    @patch('api.views.attendance_now')
    def test_makeup_can_be_revoked_and_regranted_without_losing_audit(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        self.client.force_authenticate(self.admin)
        grant_response = self.post_makeup(session)
        record_id = grant_response.data['record_id']

        revoke_response = self.client.post(
            f'/api/attendance/admin/makeups/{record_id}/revoke/',
            {'reason': '管理员核对后确认选择了错误学员'},
            format='json',
        )
        repeated_revoke = self.client.post(
            f'/api/attendance/admin/makeups/{record_id}/revoke/',
            {'reason': '再次尝试撤销已经撤销的补签'},
            format='json',
        )
        overview_after_revoke = self.client.get('/api/attendance/admin/overview/?date=2026-07-15')
        regrant_response = self.post_makeup(
            session,
            reason='重新核对后确认该学员确实到场',
        )

        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(repeated_revoke.status_code, 409)
        morning = next(item for item in overview_after_revoke.data['slots'] if item['slot'] == 'morning')
        self.assertEqual(morning['signed_count'], 0)
        self.assertIn(self.student.id, [item['student_id'] for item in morning['absent_students']])
        self.assertEqual(regrant_response.status_code, 201)
        self.assertTrue(regrant_response.data['reactivated'])
        self.assertEqual(regrant_response.data['record_id'], record_id)

        record = AttendanceRecord.objects.get(pk=record_id)
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertIsNone(record.revoked_by)
        self.assertIsNone(record.revoked_at)
        self.assertEqual(record.revoke_reason, '')
        self.assertEqual(
            list(record.audit_logs.order_by('id').values_list('action', flat=True)),
            [
                AttendanceAuditLog.Action.GRANT,
                AttendanceAuditLog.Action.REVOKE,
                AttendanceAuditLog.Action.GRANT,
            ],
        )

    @patch('api.views.attendance_now')
    def test_normal_sign_in_cannot_be_revoked_through_makeup_endpoint(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        record = AttendanceRecord.objects.create(session=session, student=self.student)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            f'/api/attendance/admin/makeups/{record.id}/revoke/',
            {'reason': '尝试撤销学员自己完成的正常签到'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertFalse(AttendanceAuditLog.objects.exists())

    @patch('api.views.attendance_now')
    def test_revoke_requires_admin_and_rejects_spoofed_or_short_reason(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        record = AttendanceRecord.objects.create(
            session=session,
            student=self.student,
            source=AttendanceRecord.Source.ADMIN_MAKEUP,
            recorded_by=self.admin,
            makeup_reason='管理员现场确认学员已经到场',
        )
        endpoint = f'/api/attendance/admin/makeups/{record.id}/revoke/'

        anonymous_response = self.client.post(
            endpoint,
            {'reason': '匿名用户尝试撤销补签记录'},
            format='json',
        )
        self.client.force_authenticate(self.student)
        student_response = self.client.post(
            endpoint,
            {'reason': '学员尝试撤销补签记录'},
            format='json',
        )
        self.client.force_authenticate(self.admin)
        spoofed_response = self.client.post(
            endpoint,
            {
                'reason': '管理员提交包含伪造字段的撤销请求',
                'revoked_by': self.student.id,
                'status': AttendanceRecord.Status.REVOKED,
            },
            format='json',
        )
        short_reason_response = self.client.post(
            endpoint,
            {'reason': '太短'},
            format='json',
        )

        self.assertEqual(anonymous_response.status_code, 401)
        self.assertEqual(student_response.status_code, 403)
        self.assertEqual(spoofed_response.status_code, 400)
        self.assertEqual(short_reason_response.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertFalse(AttendanceAuditLog.objects.exists())

    @patch('api.views.attendance_now')
    def test_admin_overview_uses_membership_and_exposes_makeup_metadata(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        outsider = User.objects.create_user(username='overview-outsider', password='Pass12345!')
        self.client.force_authenticate(self.admin)
        self.post_makeup(session)

        response = self.client.get('/api/attendance/admin/overview/?date=2026-07-15')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student_count'], 2)
        morning = next(item for item in response.data['slots'] if item['slot'] == 'morning')
        self.assertTrue(morning['can_makeup'])
        self.assertEqual(morning['signed_count'], 1)
        record = morning['records'][0]
        self.assertEqual(record['source'], AttendanceRecord.Source.ADMIN_MAKEUP)
        self.assertEqual(record['source_label'], '管理员补签')
        self.assertEqual(record['recorded_by']['username'], self.admin.username)
        self.assertTrue(record['makeup_reason'])
        self.assertTrue(record['can_revoke'])
        all_usernames = [record['username']] + [item['username'] for item in morning['absent_students']]
        self.assertNotIn(outsider.username, all_usernames)

    @patch('api.views.attendance_now')
    def test_student_today_shows_makeup_label_without_admin_details(self, mocked_now):
        mocked_now.return_value = self.local_datetime(10)
        session = self.generate_morning_session()
        AttendanceRecord.objects.create(
            session=session,
            student=self.student,
            source=AttendanceRecord.Source.ADMIN_MAKEUP,
            recorded_by=self.admin,
            makeup_reason='管理员现场核实学员已经到场',
        )
        self.client.force_authenticate(self.student)

        response = self.client.get('/api/attendance/today/')

        self.assertEqual(response.status_code, 200)
        morning = next(item for item in response.data['slots'] if item['slot'] == 'morning')
        self.assertEqual(morning['source_label'], '管理员补签')
        self.assertNotIn('makeup_reason', str(response.data))
        self.assertNotIn('recorded_by', str(response.data))
        self.assertNotIn('revoke_reason', str(response.data))

    @patch('api.views.attendance_now')
    def test_non_member_student_cannot_view_or_submit_attendance(self, mocked_now):
        mocked_now.return_value = self.local_datetime(9)
        self.generate_morning_session()
        outsider = User.objects.create_user(username='attendance-no-membership', password='Pass12345!')
        self.client.force_authenticate(outsider)

        today_response = self.client.get('/api/attendance/today/')
        check_in_response = self.client.post('/api/attendance/check-in/', {'code': '1234'}, format='json')

        self.assertEqual(today_response.status_code, 403)
        self.assertEqual(check_in_response.status_code, 403)
        self.assertFalse(AttendanceRecord.objects.filter(student=outsider).exists())

    def test_database_rejects_inconsistent_makeup_metadata(self):
        session = self.generate_morning_session()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceRecord.objects.create(
                    session=session,
                    student=self.student,
                    source=AttendanceRecord.Source.ADMIN_MAKEUP,
                    makeup_reason='缺少操作管理员的非法补签记录',
                )

    def test_database_defaults_keep_legacy_normal_sign_in_inserts_compatible(self):
        session = self.generate_morning_session()

        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO api_attendancerecord (session_id, student_id, signed_at) '
                'VALUES (%s, %s, %s)',
                [session.id, self.student.id, timezone.now()],
            )

        record = AttendanceRecord.objects.get(session=session, student=self.student)
        self.assertEqual(record.source, AttendanceRecord.Source.CODE)
        self.assertEqual(record.status, AttendanceRecord.Status.ACTIVE)
        self.assertEqual(record.makeup_reason, '')
        self.assertEqual(record.revoke_reason, '')

    @patch('api.views.attendance_now')
    def test_makeup_and_revoke_lock_base_rows_in_user_first_order(self, mocked_now):
        mocked_now.return_value = self.local_datetime(13)
        session = self.generate_morning_session()
        self.client.force_authenticate(self.admin)
        lock_models = []
        related_after_lock = []
        related_before_lock = []
        original_select_for_update = QuerySet.select_for_update
        original_select_related = QuerySet.select_related

        def track_select_for_update(queryset, *args, **kwargs):
            lock_models.append(queryset.model)
            if queryset.query.select_related:
                related_before_lock.append(queryset.model)
            return original_select_for_update(queryset, *args, **kwargs)

        def track_select_related(queryset, *fields):
            if queryset.query.select_for_update:
                related_after_lock.append((queryset.model, fields))
            return original_select_related(queryset, *fields)

        with patch.object(QuerySet, 'select_for_update', track_select_for_update), patch.object(
            QuerySet,
            'select_related',
            track_select_related,
        ):
            grant_response = self.post_makeup(session)

        self.assertEqual(grant_response.status_code, 201)
        self.assertEqual(lock_models, [User, AttendanceRecord])
        self.assertEqual(related_before_lock, [])
        self.assertEqual(related_after_lock, [])

        lock_models.clear()
        related_before_lock.clear()
        related_after_lock.clear()
        makeup_record_id = grant_response.data['record_id']
        with patch.object(QuerySet, 'select_for_update', track_select_for_update), patch.object(
            QuerySet,
            'select_related',
            track_select_related,
        ):
            revoke_response = self.client.post(
                f'/api/attendance/admin/makeups/{makeup_record_id}/revoke/',
                {'reason': '管理员复核后确认需要撤销补签'},
                format='json',
            )

        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(lock_models, [User, AttendanceRecord])
        self.assertEqual(related_before_lock, [])
        self.assertEqual(related_after_lock, [])
