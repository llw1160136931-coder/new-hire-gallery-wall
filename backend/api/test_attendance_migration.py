from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AttendanceMakeupMigrationTests(TransactionTestCase):
    migrate_from = [('api', '0014_profile_training_group')]
    migrate_to = [('api', '0015_attendance_makeup')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_latest_schema)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        User = old_apps.get_model('auth', 'User')
        Profile = old_apps.get_model('api', 'Profile')
        TrainingCamp = old_apps.get_model('api', 'TrainingCamp')
        AttendanceSession = old_apps.get_model('api', 'AttendanceSession')
        AttendanceRecord = old_apps.get_model('api', 'AttendanceRecord')

        camp = TrainingCamp.objects.filter(is_active=True).first()
        if camp:
            TrainingCamp.objects.filter(pk=camp.pk).update(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
        else:
            camp = TrainingCamp.objects.create(
                name='历史培训期',
                slug='historical-attendance-camp',
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
                is_active=True,
            )

        active_student = User.objects.create(
            username='historical-active-student',
            password='!',
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        Profile.objects.create(
            user_id=active_student.id,
            name='历史启用学员',
            role='student',
        )
        inactive_student = User.objects.create(
            username='historical-inactive-student',
            password='!',
            is_active=False,
            is_staff=False,
            is_superuser=False,
        )
        Profile.objects.create(
            user_id=inactive_student.id,
            name='历史停用学员',
            role='student',
        )

        session = AttendanceSession.objects.create(
            camp_id=camp.id,
            date=date(2026, 7, 15),
            time_slot='morning',
            code='1234',
        )
        record = AttendanceRecord.objects.create(
            session_id=session.id,
            student_id=active_student.id,
        )
        self.active_student_id = active_student.id
        self.inactive_student_id = inactive_student.id
        self.camp_id = camp.id
        self.record_id = record.id

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    @staticmethod
    def _restore_latest_schema():
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_active_students_and_normal_records_are_backfilled(self):
        AttendanceRecord = self.apps.get_model('api', 'AttendanceRecord')
        TrainingCampMembership = self.apps.get_model('api', 'TrainingCampMembership')

        record = AttendanceRecord.objects.get(pk=self.record_id)
        self.assertEqual(record.source, 'code')
        self.assertEqual(record.status, 'active')
        self.assertIsNone(record.recorded_by_id)
        self.assertEqual(record.makeup_reason, '')
        self.assertIsNone(record.revoked_by_id)
        self.assertIsNone(record.revoked_at)
        self.assertEqual(record.revoke_reason, '')
        self.assertTrue(
            TrainingCampMembership.objects.filter(
                camp_id=self.camp_id,
                student_id=self.active_student_id,
            ).exists()
        )
        self.assertFalse(
            TrainingCampMembership.objects.filter(
                camp_id=self.camp_id,
                student_id=self.inactive_student_id,
            ).exists()
        )
