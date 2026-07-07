from datetime import date, time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from api.models import Course, Profile, Work


class Command(BaseCommand):
    help = 'Seed demo users, courses, and works for local development.'

    def handle(self, *args, **options):
        admin = self.ensure_user('admin', 'Admin12345', '审核管理员', Profile.Role.ADMIN, is_staff=True)
        student = self.ensure_user('student', 'Student12345', '新员工', Profile.Role.STUDENT)
        self.seed_courses()
        self.seed_works(student, admin)
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
        profile.school = '浙江大学' if role == Profile.Role.STUDENT else ''
        profile.gender = Profile.Gender.UNKNOWN
        profile.zodiac = '天秤座' if role == Profile.Role.STUDENT else ''
        profile.mbti = 'ENFP' if role == Profile.Role.STUDENT else ''
        profile.bio = '正在把培训中的每一次练习，整理成可以被看见的作品。'
        profile.save()
        return user

    def seed_courses(self):
        rows = [
            ('2026-07-18', time(9, 0), time(10, 30), '开营仪式与破冰', '培训项目组', '报告厅', Course.Status.DONE),
            ('2026-07-18', time(14, 0), time(16, 0), '企业文化导入', '人力资源部', '培训室 A', Course.Status.DONE),
            ('2026-07-19', time(9, 30), time(11, 30), '业务地图与组织协作', '运营管理部', '培训室 B', Course.Status.UPCOMING),
            ('2026-07-20', time(9, 0), time(11, 30), 'AI 工具基础与提示词实践', '数智化团队', '创新教室', Course.Status.LIVE),
            ('2026-07-20', time(15, 0), time(16, 30), '作品选题工作坊', '导师组', '协作区', Course.Status.UPCOMING),
            ('2026-07-21', time(10, 0), time(11, 30), '产品思维与用户洞察', '产品中心', '培训室 A', Course.Status.UPCOMING),
            ('2026-07-22', time(9, 30), time(11, 0), '数据安全与合规', '信息安全部', '培训室 B', Course.Status.UPCOMING),
            ('2026-07-23', time(14, 0), time(16, 30), 'AI 作品打磨', '数智化团队', '创新教室', Course.Status.UPCOMING),
            ('2026-07-24', time(10, 0), time(12, 0), '结业路演彩排', '培训项目组', '报告厅', Course.Status.UPCOMING),
            ('2026-07-25', time(9, 30), time(11, 30), '结业路演与作品投票', '评审团', '报告厅', Course.Status.UPCOMING),
        ]
        for index, (day, start, end, title, teacher, room, status) in enumerate(rows):
            Course.objects.update_or_create(
                date=date.fromisoformat(day),
                start_time=start,
                title=title,
                defaults={
                    'end_time': end,
                    'teacher': teacher,
                    'room': room,
                    'status': status,
                    'sort_order': index,
                },
            )

    def seed_works(self, student, admin):
        works = [
            ('AI 入职欢迎海报', Work.WorkType.AI, Work.Status.APPROVED, '用 AI 生成视觉草图，再结合培训关键词完成新人欢迎海报。'),
            ('培训流程小程序原型', Work.WorkType.TRAINING, Work.Status.APPROVED, '覆盖签到、任务提交、课程提醒和作品投票的轻量原型。'),
            ('部门知识地图', Work.WorkType.TRAINING, Work.Status.PENDING, '把部门职责、协作对象和常用系统整理成一张上手地图。'),
        ]
        for title, work_type, status, description in works:
            Work.objects.update_or_create(
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
