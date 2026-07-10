from datetime import date, time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from api.models import Course, Profile, Tag, TrainingCamp, Work, normalize_tag_name


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
        profile.school = '浙江大学' if role == Profile.Role.STUDENT else ''
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
        rows = [
            ('2026-07-19', time(14, 0), time(14, 0), '新员工报到', '电信大厦3楼大会议室', '报到', '报到', '——'),
            ('2026-07-19', time(14, 0), time(14, 40), '新员工报到', '电信大厦3楼大会议室', '团队建设', '介绍培训整体安排、学员分组、团队组建。', '工作人员'),
            ('2026-07-19', time(14, 40), time(16, 0), '新员工报到', '电信大厦3楼大会议室', '团队建设', 'AI 初体验：AI知识分享及活动安排', '工作人员'),
            ('2026-07-19', time(16, 0), time(17, 0), '新员工报到', '白云学堂', '分批前往白云学堂', '分批前往白云学堂', '工作人员'),
            ('2026-07-19', time(19, 0), time(20, 30), '新员工报到', '白云学堂', '晚间活动', '匹克球主题游戏活动', '工作人员'),
            ('2026-07-20', time(9, 0), time(12, 0), '融入团队', '白云学堂+白云山', '拓展训练', '团队拓展活动', '外部师资'),
            ('2026-07-20', time(14, 0), time(17, 30), '融入团队', '白云学堂+白云山', '拓展训练', '团队拓展活动', '外部师资'),
            ('2026-07-20', time(19, 0), time(20, 30), '融入团队', '白云学堂', '晚间活动', 'AI Agent、编程专题分享会', '工作人员'),
            ('2026-07-21', time(9, 0), time(9, 15), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '合影', '新入职员工与高总合影', '/'),
            ('2026-07-21', time(9, 15), time(10, 15), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '高红潮总经理讲话', '欢迎新员工入职并表达要求与期望', '高总'),
            ('2026-07-21', time(10, 25), time(11, 50), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '企业概况介绍', '企业简介及人力资源管理体系概述', '张小平'),
            ('2026-07-21', time(14, 0), time(14, 50), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '市场运营概况', '市场运营概况', '周佩钰'),
            ('2026-07-21', time(15, 0), time(15, 50), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '网络运营概况', '网络运营概况', '袁庆洪'),
            ('2026-07-21', time(16, 0), time(16, 50), '总经理座谈交流及企业概况', '电信大厦3楼大会议室', '政企营销概况', '政企营销概况', '李芹'),
            ('2026-07-21', time(16, 50), time(18, 0), '总经理座谈交流及企业概况', '电信大厦23楼', '参观', '电信大厦23楼：AI+数字展厅及行业创新体验中心', '讲解员'),
            ('2026-07-22', time(9, 0), time(12, 0), 'AI前沿学习及电信体验参观', '白云学堂', 'AI实战赋能：新时代的职场效率革命', 'AI实战赋能：新时代的职场效率革命', '冯前进'),
            ('2026-07-22', time(14, 0), time(17, 0), 'AI前沿学习及电信体验参观', '中国电信创新孵化基地', '中国电信创新孵化基地', '中国电信创新孵化基地', '讲解员'),
            ('2026-07-22', time(19, 0), time(20, 30), 'AI前沿学习及电信体验参观', '白云学堂', '晚间活动', '匹克球主题游戏活动', '工作人员'),
            ('2026-07-23', time(9, 0), time(10, 0), '劳模精神及应知应会', '白云学堂', '劳模精神', '践行劳模劳动工匠精神', '邓艳梅'),
            ('2026-07-23', time(10, 10), time(10, 50), '劳模精神及应知应会', '白云学堂', '员工关怀体系介绍', '介绍工会方面员工关怀政策', '黄城'),
            ('2026-07-23', time(11, 0), time(11, 40), '劳模精神及应知应会', '白云学堂', '自觉廉洁从业，成就美好未来', '新员工廉洁警示专题教育、八项规定', '魏鸿'),
            ('2026-07-23', time(14, 0), time(14, 40), '劳模精神及应知应会', '白云学堂', '企业文化及红色精神', '企业文化概况、红色精神', '王永杰'),
            ('2026-07-23', time(14, 50), time(15, 20), '劳模精神及应知应会', '白云学堂', '保密工作', '保密工作概况', '钟海霞'),
            ('2026-07-23', time(15, 30), time(16, 0), '劳模精神及应知应会', '白云学堂', '用户个人信息保护法律', '用户个人信息保护相关法律知识宣贯', '罗晓风'),
            ('2026-07-23', time(16, 0), time(16, 30), '劳模精神及应知应会', '白云学堂', '网络信息安全', '网络信息安全知识', '曾礼荣'),
            ('2026-07-23', time(16, 40), time(17, 10), '劳模精神及应知应会', '白云学堂', '安全生产', '安全生产', '黄剑锋'),
            ('2026-07-23', time(19, 0), time(20, 30), '劳模精神及应知应会', '白云学堂', '晚间活动', 'AI成果分享会', '工作人员'),
            ('2026-07-24', time(9, 0), time(11, 30), '优秀代表经验分享', '白云学堂', '四级经理代表分享', '1、四级经理代表分享个人成长规划\n2、广州分公司自主研发运营情况\n3、战新业务介绍', '时瑞'),
            ('2026-07-24', time(14, 0), time(14, 40), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '小CEO代表：如何通过岗位工作提升个人价值', '从化分公司蔡海坚'),
            ('2026-07-24', time(14, 40), time(15, 20), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '员工代表：如何成长为技术专家', '业支中心戴亨玮'),
            ('2026-07-24', time(15, 30), time(16, 10), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '员工代表：如何成长为技能人才', '增城分公司智云支局吴浅灿'),
            ('2026-07-24', time(16, 10), time(16, 50), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '员工代表：“从新人到熟手”的心路历程', '战新中心李星颖'),
        ]
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
