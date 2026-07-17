from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from api.models import Course, Profile, Tag, TrainingCamp, Work, normalize_tag_name
from api.training_schedule import COURSE_SCHEDULE


class Command(BaseCommand):
    help = 'Seed demo users, courses, and works for local development.'

    def handle(self, *args, **options):
        admin = self.ensure_user('admin', 'Admin12345', '审核管理员', Profile.Role.ADMIN, is_staff=True)
        student = self.ensure_user('student', 'Student12345', '新员工', Profile.Role.STUDENT)
        camp = self.ensure_camp()
        self.seed_courses(camp)
        self.seed_works(camp, student, admin)
        self.stdout.write(self.style.SUCCESS('Demo data ready.'))
        self.stdout.write('Admin login: admin / Admin12345')
        self.stdout.write('Student login: student / Student12345')

    def ensure_user(self, username, password, name, role, is_staff=False):
        user, _ = User.objects.get_or_create(username=username)
        user.is_staff = is_staff
        user.is_superuser = is_staff
        user.set_password(password)
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user, defaults={'name': name, 'role': role})
        profile.name = name
        profile.role = role
        profile.workplace = '示例科技公司' if role == Profile.Role.STUDENT else ''
        profile.gender = Profile.Gender.UNKNOWN
        profile.zodiac = '天秤座' if role == Profile.Role.STUDENT else ''
        profile.mbti = 'ENFP' if role == Profile.Role.STUDENT else ''
        profile.bio = '正在把培训中的每一次练习，整理成可以被看见的作品。'
        profile.save()
        return user

    def ensure_camp(self):
        camp = TrainingCamp.get_active()
        if not camp:
            camp = TrainingCamp(slug='new-hire-2026', is_active=True)
        camp.name = '2026 新员工训练营'
        camp.start_date = date(2026, 7, 19)
        camp.end_date = date(2026, 7, 24)
        camp.vote_limit = 5
        camp.save()
        return camp

    def seed_courses(self, camp):
        rows = COURSE_SCHEDULE
        camp.courses.all().delete()
        for index, (day, start, end, topic, room, title, content, teacher) in enumerate(rows):
            Course.objects.update_or_create(
                camp=camp,
                date=date.fromisoformat(day),
                start_time=start,
                title=title,
                defaults={
                    'end_time': end,
                    'topic': topic,
                    'content': content,
                    'teacher': teacher,
                    'room': room,
                    'status': Course.Status.UPCOMING,
                    'sort_order': index,
                },
            )

    def seed_works(self, camp, student, admin):
        works = [
            ('AI 入职欢迎海报', Work.WorkType.AI, Work.Status.APPROVED, '用 AI 生成视觉草图，再结合培训关键词完成新人欢迎海报。', ['AI 海报']),
            ('培训流程小程序原型', Work.WorkType.TRAINING, Work.Status.APPROVED, '覆盖签到、任务提交、课程提醒和作品投票的轻量原型。', ['流程 Demo']),
            ('部门知识地图', Work.WorkType.TRAINING, Work.Status.PENDING, '把部门职责、协作对象和常用系统整理成一张上手地图。', ['知识地图']),
        ]
        for title, work_type, status, description, tag_names in works:
            work, _ = Work.objects.update_or_create(
                camp=camp,
                author=student,
                title=title,
                defaults={
                    'work_type': work_type,
                    'status': status,
                    'description': description,
                    'link': 'https://example.com',
                    'reviewed_by': admin if status == Work.Status.APPROVED else None,
                },
            )
            tags = [
                Tag.objects.get_or_create(
                    normalized_name=normalize_tag_name(name),
                    defaults={'name': name},
                )[0]
                for name in tag_names
            ]
            work.tags.set(tags)
