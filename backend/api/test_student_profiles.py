import shutil
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APITestCase

from .models import Profile


TEST_DIR = Path(__file__).resolve().parent / '.test_student_profile_imports'


class ImportStudentProfilesTests(TestCase):
    def setUp(self):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        self.first = User.objects.create_user(username='student-a', password='OriginalPass123!')
        self.first.profile.name = '学员甲'
        self.first.profile.save(update_fields=['name'])
        self.second = User.objects.create_user(username='student-b', password='OriginalPass456!')
        self.second.profile.name = '学员乙'
        self.second.profile.mbti = Profile.Mbti.INFP
        self.second.profile.save(update_fields=['name', 'mbti'])

    def tearDown(self):
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def make_workbook(self, rows, filename='profiles.xlsx'):
        path = TEST_DIR / filename
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = '学员资料'
        worksheet.append(['姓名', 'MBTI类型', '小组'])
        for row in rows:
            worksheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def test_dry_run_does_not_modify_profiles_or_passwords(self):
        path = self.make_workbook([
            ['学员甲', 'ENFP（竞选者）', '第2组'],
            ['学员乙', '', '第3组'],
        ])
        password_hashes = {
            self.first.pk: self.first.password,
            self.second.pk: self.second.password,
        }

        output = StringIO()
        call_command('import_student_profiles', path, dry_run=True, stdout=output)

        self.first.profile.refresh_from_db()
        self.second.profile.refresh_from_db()
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.profile.mbti, '')
        self.assertEqual(self.first.profile.training_group, '')
        self.assertEqual(self.second.profile.mbti, Profile.Mbti.INFP)
        self.assertEqual(self.second.profile.training_group, '')
        self.assertEqual(self.first.password, password_hashes[self.first.pk])
        self.assertEqual(self.second.password, password_hashes[self.second.pk])
        self.assertIn('数据库未改动', output.getvalue())

    def test_import_normalizes_values_clears_blank_mbti_and_keeps_passwords(self):
        path = self.make_workbook([
            ['学员甲', 'enfp（竞选者）', '第 2 组'],
            ['学员乙', '', '3'],
        ])
        first_password = self.first.password
        second_password = self.second.password

        call_command('import_student_profiles', path, stdout=StringIO())

        self.first.profile.refresh_from_db()
        self.second.profile.refresh_from_db()
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.profile.mbti, Profile.Mbti.ENFP)
        self.assertEqual(self.first.profile.training_group, Profile.TrainingGroup.GROUP_2)
        self.assertEqual(self.first.profile.get_training_group_display(), '第2组')
        self.assertEqual(self.second.profile.mbti, '')
        self.assertEqual(self.second.profile.training_group, Profile.TrainingGroup.GROUP_3)
        self.assertEqual(self.first.password, first_password)
        self.assertEqual(self.second.password, second_password)

    def test_missing_student_aborts_entire_import(self):
        path = self.make_workbook([
            ['学员甲', 'ENFP', '第1组'],
            ['不存在的学员', 'ISTJ', '第2组'],
        ])

        with self.assertRaises(CommandError):
            call_command('import_student_profiles', path, stdout=StringIO())

        self.first.profile.refresh_from_db()
        self.assertEqual(self.first.profile.mbti, '')
        self.assertEqual(self.first.profile.training_group, '')

    def test_duplicate_name_and_admin_matches_are_rejected(self):
        duplicate = User.objects.create_user(username='student-a-copy', password='Pass12345!')
        duplicate.profile.name = '学员甲'
        duplicate.profile.save(update_fields=['name'])
        admin = User.objects.create_user(username='profile-admin', password='Pass12345!', is_staff=True)
        admin.profile.name = '管理员甲'
        admin.profile.role = Profile.Role.ADMIN
        admin.profile.save(update_fields=['name', 'role'])
        path = self.make_workbook([
            ['学员甲', 'ENFP', '第1组'],
            ['管理员甲', 'ISTJ', '第2组'],
        ])

        with self.assertRaises(CommandError) as context:
            call_command('import_student_profiles', path, stdout=StringIO())

        message = str(context.exception)
        self.assertIn('多个同名账号', message)
        self.assertIn('管理员账号', message)

    def test_invalid_mbti_and_group_are_rejected(self):
        path = self.make_workbook([
            ['学员甲', 'ABCD', '第9组'],
        ])

        with self.assertRaises(CommandError) as context:
            call_command('import_student_profiles', path, stdout=StringIO())

        message = str(context.exception)
        self.assertIn('不支持的 MBTI', message)
        self.assertIn('第1组至第6组', message)


class ProfileTrainingGroupApiTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username='readonly-group', password='Pass12345!')
        self.student.profile.name = '只读分组学员'
        self.student.profile.training_group = Profile.TrainingGroup.GROUP_2
        self.student.profile.save(update_fields=['name', 'training_group'])
        self.client.force_authenticate(self.student)

    def test_student_cannot_change_training_group_through_profile_api(self):
        response = self.client.patch('/api/me/', {
            'training_group': Profile.TrainingGroup.GROUP_6,
            'mbti': Profile.Mbti.ENFP,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.training_group, Profile.TrainingGroup.GROUP_2)
        self.assertEqual(self.student.profile.mbti, Profile.Mbti.ENFP)
        self.assertEqual(response.data['training_group'], Profile.TrainingGroup.GROUP_2)
        self.assertEqual(response.data['training_group_label'], '第2组')


    def test_group_label_is_returned_and_can_be_searched(self):
        me_response = self.client.get('/api/me/')
        search_response = self.client.get('/api/search/?q=%E7%AC%AC2%E7%BB%84')

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data['training_group_label'], '第2组')
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.data['profiles'][0]['name'], '只读分组学员')
        self.assertEqual(search_response.data['profiles'][0]['training_group_label'], '第2组')
