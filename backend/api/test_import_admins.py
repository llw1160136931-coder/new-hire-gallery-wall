import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook

from .models import Profile


class ImportAdminsCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_workbook(self, rows):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = '管理员账号'
        worksheet.append(['姓名', '账号', '密码', '角色'])
        for row in rows:
            worksheet.append(row)
        path = Path(self.temp_dir.name) / 'admins.xlsx'
        workbook.save(path)
        workbook.close()
        return path

    def test_dry_run_does_not_write_or_print_password(self):
        password = 'Admin!9xQ2026Safe'
        path = self.make_workbook([
            ['审核员甲', 'reviewer-a', password, '管理员'],
        ])
        output = StringIO()

        call_command('import_admins', path, dry_run=True, stdout=output)

        self.assertFalse(User.objects.filter(username='reviewer-a').exists())
        self.assertIn('数据库未改动', output.getvalue())
        self.assertNotIn(password, output.getvalue())

    def test_import_creates_hashed_non_superuser_admin(self):
        password = 'Admin!7zM2026Safe'
        path = self.make_workbook([
            ['审核员乙', 'reviewer-b', password, '管理员'],
        ])

        call_command('import_admins', path, stdout=StringIO())

        user = User.objects.get(username='reviewer-b')
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.name, '审核员乙')
        self.assertEqual(user.profile.role, Profile.Role.ADMIN)

    def test_weak_admin_password_is_always_rejected(self):
        path = self.make_workbook([
            ['审核员丙', 'reviewer-c', '123456', '管理员'],
        ])

        with self.assertRaisesMessage(CommandError, '管理员密码不符合安全要求'):
            call_command('import_admins', path, stdout=StringIO())

        self.assertFalse(User.objects.filter(username='reviewer-c').exists())

    def test_duplicate_admin_username_stops_entire_import(self):
        path = self.make_workbook([
            ['审核员甲', 'duplicate-admin', 'Admin!9xQ2026Safe', '管理员'],
            ['审核员乙', 'duplicate-admin', 'Admin!7zM2026Safe', '管理员'],
        ])

        with self.assertRaisesMessage(CommandError, '重复管理员账号'):
            call_command('import_admins', path, stdout=StringIO())

        self.assertFalse(User.objects.filter(username='duplicate-admin').exists())

    def test_superuser_cannot_be_overwritten(self):
        superuser = User.objects.create_superuser(
            username='root-admin',
            password='Root!8xQ2026Safe',
            email='root@example.com',
        )
        path = self.make_workbook([
            ['普通管理员', 'root-admin', 'Admin!9zM2026Safe', '管理员'],
        ])

        with self.assertRaisesMessage(CommandError, '超级管理员账号禁止'):
            call_command(
                'import_admins',
                path,
                update_existing=True,
                stdout=StringIO(),
            )

        superuser.refresh_from_db()
        self.assertTrue(superuser.check_password('Root!8xQ2026Safe'))
        self.assertTrue(superuser.is_superuser)
