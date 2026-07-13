import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook

from .models import Profile


class ImportStudentsCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_workbook(self, rows, headers=None):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = '学员名单'
        worksheet.append(headers or ['姓名', '账号', '工作单位', '密码', '性别', '年龄'])
        for row in rows:
            worksheet.append(row)
        path = Path(self.temp_dir.name) / 'students.xlsx'
        workbook.save(path)
        workbook.close()
        return path

    def test_dry_run_validates_without_writing_or_printing_passwords(self):
        password = 'Alpha!9xQ2026'
        path = self.make_workbook([
            ['张三', 'zhangsan', '示例科技公司', password, '男', 23],
        ])
        output = StringIO()

        call_command('import_students', path, dry_run=True, stdout=output)

        self.assertFalse(User.objects.filter(username='zhangsan').exists())
        self.assertIn('数据库未改动', output.getvalue())
        self.assertNotIn(password, output.getvalue())

    def test_import_creates_student_and_hashes_password(self):
        password = 'Beta!7zM2026'
        path = self.make_workbook([
            ['李四', 'lisi', '示例科技公司', password, '女', 24],
        ])

        call_command('import_students', path, stdout=StringIO())

        user = User.objects.get(username='lisi')
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.profile.name, '李四')
        self.assertEqual(user.profile.workplace, '示例科技公司')
        self.assertEqual(user.profile.gender, Profile.Gender.FEMALE)
        self.assertEqual(user.profile.role, Profile.Role.STUDENT)

    def test_duplicate_username_in_excel_stops_entire_import(self):
        path = self.make_workbook([
            ['张三', 'duplicate', '甲单位', 'Alpha!9xQ2026', '男', 23],
            ['李四', 'duplicate', '乙单位', 'Beta!7zM2026', '女', 24],
        ])

        with self.assertRaisesMessage(CommandError, 'Excel 内存在重复账号'):
            call_command('import_students', path, stdout=StringIO())

        self.assertFalse(User.objects.filter(username='duplicate').exists())

    def test_existing_account_requires_explicit_update_flag(self):
        existing = User.objects.create_user(username='existing', password='Old!8xQ2026')
        existing.profile.name = '旧姓名'
        existing.profile.save(update_fields=['name'])
        path = self.make_workbook([
            ['新姓名', 'existing', '新单位', 'New!9zM2026', '其他', 25],
        ])

        with self.assertRaisesMessage(CommandError, '账号已存在'):
            call_command('import_students', path, stdout=StringIO())

        existing.refresh_from_db()
        self.assertTrue(existing.check_password('Old!8xQ2026'))

        call_command('import_students', path, update_existing=True, stdout=StringIO())
        existing.refresh_from_db()
        existing.profile.refresh_from_db()
        self.assertTrue(existing.check_password('New!9zM2026'))
        self.assertEqual(existing.profile.name, '新姓名')
        self.assertEqual(existing.profile.workplace, '新单位')

    def test_weak_password_requires_explicit_override(self):
        path = self.make_workbook([
            ['王五', 'wangwu', '示例科技公司', '123456', '男', 22],
        ])

        with self.assertRaisesMessage(CommandError, '密码不符合安全要求'):
            call_command('import_students', path, stdout=StringIO())

        call_command(
            'import_students',
            path,
            allow_weak_passwords=True,
            stdout=StringIO(),
        )
        user = User.objects.get(username='wangwu')
        self.assertTrue(user.check_password('123456'))

    def test_profile_admin_cannot_be_overwritten_as_student(self):
        admin = User.objects.create_user(username='profile-admin', password='Old!8xQ2026')
        admin.profile.role = Profile.Role.ADMIN
        admin.profile.save(update_fields=['role'])
        path = self.make_workbook([
            ['普通学员', 'profile-admin', '示例科技公司', 'New!9zM2026', '男', 22],
        ])

        with self.assertRaisesMessage(CommandError, '账号属于管理员'):
            call_command(
                'import_students',
                path,
                update_existing=True,
                stdout=StringIO(),
            )

        admin.refresh_from_db()
        admin.profile.refresh_from_db()
        self.assertTrue(admin.check_password('Old!8xQ2026'))
        self.assertEqual(admin.profile.role, Profile.Role.ADMIN)
