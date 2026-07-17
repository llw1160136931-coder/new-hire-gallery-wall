from collections import Counter
from datetime import date, time
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Course, CourseResource, TrainingCamp
from .training_schedule import COURSE_SCHEDULE


class TrainingScheduleDefinitionTests(TestCase):
    def test_current_schedule_is_complete(self):
        daily_counts = Counter(day for day, *_ in COURSE_SCHEDULE)

        self.assertEqual(len(COURSE_SCHEDULE), 27)
        self.assertEqual(
            daily_counts,
            {
                '2026-07-19': 4,
                '2026-07-20': 2,
                '2026-07-21': 6,
                '2026-07-22': 2,
                '2026-07-23': 8,
                '2026-07-24': 5,
            },
        )
        self.assertTrue(all(topic and room and title and teacher for _, _, _, topic, room, title, _, teacher in COURSE_SCHEDULE))
        self.assertEqual(sum(content == '' for *_, content, _ in COURSE_SCHEDULE), 2)


class TrainingScheduleMigrationTests(TestCase):
    def setUp(self):
        TrainingCamp.objects.filter(is_active=True).update(is_active=False)
        self.camp = TrainingCamp.objects.create(
            name='2026 新员工训练营',
            slug='schedule-migration-test',
            start_date=date(2026, 7, 19),
            end_date=date(2026, 7, 24),
            is_active=True,
        )
        self.visit = Course.objects.create(
            camp=self.camp,
            date=date(2026, 7, 21),
            start_time=time(16, 50),
            end_time=time(18, 0),
            topic='总经理座谈交流及企业概况',
            room='电信大厦23楼',
            title='参观',
            content='电信大厦23楼：AI+数字展厅及行业创新体验中心',
            teacher='讲解员',
            sort_order=14,
        )
        Course.objects.create(
            camp=self.camp,
            date=date(2026, 7, 19),
            start_time=time(14, 0),
            end_time=time(14, 0),
            topic='新员工报到',
            room='电信大厦3楼大会议室',
            title='报到',
            content='报到',
            teacher='——',
        )
        Course.objects.create(
            camp=self.camp,
            date=date(2026, 7, 23),
            start_time=time(9, 0),
            end_time=time(10, 0),
            topic='劳模精神及应知应会',
            room='白云学堂',
            title='劳模精神',
            content='践行劳模劳动工匠精神',
            teacher='邓艳梅',
        )
        self.resource = CourseResource.objects.create(
            course=self.visit,
            file='course-resources/legacy.pdf',
            original_filename='legacy.pdf',
            content_type='application/pdf',
            file_size=123,
        )
        self.obsolete = Course.objects.create(
            camp=self.camp,
            date=date(2026, 7, 22),
            start_time=time(19, 0),
            end_time=time(20, 30),
            topic='AI前沿学习及电信体验参观',
            room='白云学堂',
            title='晚间活动',
            content='匹克球主题游戏活动',
            teacher='工作人员',
        )
        self.migration = import_module('api.migrations.0012_update_2026_training_schedule')

    def apply_schedule_migration(self):
        self.migration.update_training_schedule(django_apps, None)

    def test_migration_reconciles_schedule_and_preserves_course_materials(self):
        self.apply_schedule_migration()
        self.apply_schedule_migration()

        courses = Course.objects.filter(camp=self.camp).order_by('sort_order')
        daily_counts = Counter(course.date.isoformat() for course in courses)

        self.assertEqual(courses.count(), 27)
        self.assertEqual(
            [
                (
                    course.date.isoformat(),
                    course.start_time,
                    course.end_time,
                    course.topic,
                    course.room,
                    course.title,
                    course.content,
                    course.teacher,
                )
                for course in courses
            ],
            list(COURSE_SCHEDULE),
        )
        self.assertEqual(daily_counts, {
            '2026-07-19': 4,
            '2026-07-20': 2,
            '2026-07-21': 6,
            '2026-07-22': 2,
            '2026-07-23': 8,
            '2026-07-24': 5,
        })
        self.assertEqual(list(courses.values_list('sort_order', flat=True)), list(range(27)))
        self.assertEqual(courses.filter(content='').count(), 2)
        self.assertFalse(courses.filter(topic='').exists())
        self.assertFalse(courses.filter(room='').exists())
        self.assertFalse(courses.filter(title='').exists())
        self.assertFalse(courses.filter(teacher='').exists())
        self.assertFalse(Course.objects.filter(pk=self.obsolete.pk).exists())

        self.visit.refresh_from_db()
        self.resource.refresh_from_db()
        self.assertEqual(self.visit.date, date(2026, 7, 22))
        self.assertEqual(self.visit.start_time, time(14, 0))
        self.assertEqual(self.visit.end_time, time(17, 0))
        self.assertEqual(self.visit.topic, 'AI前沿学习及电信体验参观')
        self.assertEqual(self.resource.course_id, self.visit.pk)

    def test_course_api_returns_the_updated_july_21_schedule_in_order(self):
        self.apply_schedule_migration()
        user = User.objects.create_user(username='schedule-student', password='Student12345')
        client = APIClient()
        client.force_authenticate(user)

        response = client.get('/api/courses/?date=2026-07-21')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 6)
        self.assertEqual(
            [course['start_time'][:5] for course in response.data],
            ['09:00', '09:15', '10:25', '14:00', '15:10', '16:20'],
        )
        self.assertEqual(response.data[3]['teacher'], '李槿')
        self.assertTrue(all(course['room'] == '白云学堂' for course in response.data))

    def test_migration_removes_a_stale_source_when_target_already_exists(self):
        target_visit = Course.objects.create(
            camp=self.camp,
            date=date(2026, 7, 22),
            start_time=time(14, 0),
            end_time=time(17, 0),
            topic='AI前沿学习及电信体验参观',
            room='电信大厦23楼',
            title='参观',
            content='电信大厦23楼：AI+数字展厅及行业创新体验中心',
            teacher='讲解员',
        )

        self.apply_schedule_migration()

        self.assertEqual(Course.objects.filter(camp=self.camp).count(), 27)
        self.assertTrue(Course.objects.filter(pk=target_visit.pk).exists())
        self.assertFalse(Course.objects.filter(pk=self.visit.pk).exists())
