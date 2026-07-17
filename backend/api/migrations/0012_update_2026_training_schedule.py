from datetime import date, time

from django.db import migrations


COURSES = (
    ('2026-07-19', time(14, 0), time(14, 0), '新员工报到', '电信大厦3楼大会议室', '报到', '报到', '——'),
    ('2026-07-19', time(14, 0), time(14, 40), '新员工报到', '电信大厦3楼大会议室', '团队建设', '介绍培训整体安排、学员分组、团队组建。', '工作人员'),
    ('2026-07-19', time(14, 40), time(16, 0), '新员工报到', '电信大厦3楼大会议室', '团队建设', 'AI 初体验：AI知识分享及活动安排', '工作人员'),
    ('2026-07-19', time(16, 0), time(17, 0), '新员工报到', '白云学堂', '分批前往白云学堂', '', '工作人员'),
    ('2026-07-20', time(9, 0), time(12, 0), '融入团队', '白云学堂+白云山', '拓展训练', '团队拓展活动', '外部师资'),
    ('2026-07-20', time(14, 0), time(17, 30), '融入团队', '白云学堂+白云山', '拓展训练', '团队拓展活动', '外部师资'),
    ('2026-07-21', time(9, 0), time(9, 15), '总经理座谈交流及企业概况', '白云学堂', '合影', '新入职员工与高总合影', '/'),
    ('2026-07-21', time(9, 15), time(10, 15), '总经理座谈交流及企业概况', '白云学堂', '高红潮总经理讲话', '欢迎新员工入职并表达要求与期望', '高总'),
    ('2026-07-21', time(10, 25), time(11, 50), '总经理座谈交流及企业概况', '白云学堂', '企业概况介绍', '企业简介及人力资源管理体系概述', '张小平'),
    ('2026-07-21', time(14, 0), time(15, 0), '总经理座谈交流及企业概况', '白云学堂', '市场运营概况', '市场运营概况', '李槿'),
    ('2026-07-21', time(15, 10), time(16, 10), '总经理座谈交流及企业概况', '白云学堂', '网络运营概况', '网络运营概况', '袁庆洪'),
    ('2026-07-21', time(16, 20), time(17, 20), '总经理座谈交流及企业概况', '白云学堂', '政企营销概况', '政企营销概况', '李芹'),
    ('2026-07-22', time(9, 0), time(12, 0), 'AI前沿学习及电信体验参观', '白云学堂', 'AI实战赋能：新时代的职场效率革命', '', '外部师资'),
    ('2026-07-22', time(14, 0), time(17, 0), 'AI前沿学习及电信体验参观', '电信大厦23楼', '参观', '电信大厦23楼：AI+数字展厅及行业创新体验中心', '讲解员'),
    ('2026-07-23', time(9, 0), time(10, 0), '劳模精神及应知应会', '白云学堂', '劳模精神', '践行劳模劳动工匠精神', '邓艳梅'),
    ('2026-07-23', time(10, 10), time(10, 50), '劳模精神及应知应会', '白云学堂', '员工关怀体系介绍', '介绍工会方面员工关怀政策', '黄城'),
    ('2026-07-23', time(11, 0), time(11, 40), '劳模精神及应知应会', '白云学堂', '自觉廉洁从业，成就美好未来', '新员工廉洁警示专题教育、八项规定', '魏鸿'),
    ('2026-07-23', time(14, 0), time(14, 40), '劳模精神及应知应会', '白云学堂', '企业文化及红色精神', '企业文化概况、红色精神', '王永杰'),
    ('2026-07-23', time(14, 50), time(15, 20), '劳模精神及应知应会', '白云学堂', '保密工作', '保密工作概况', '钟海霞'),
    ('2026-07-23', time(15, 30), time(16, 0), '劳模精神及应知应会', '白云学堂', '用户个人信息保护法律', '用户个人信息保护相关法律知识宣贯', '罗晓风'),
    ('2026-07-23', time(16, 0), time(16, 30), '劳模精神及应知应会', '白云学堂', '网络信息安全', '网络信息安全知识', '曾礼荣'),
    ('2026-07-23', time(16, 40), time(17, 10), '劳模精神及应知应会', '白云学堂', '安全生产', '安全生产', '黄剑锋'),
    ('2026-07-24', time(9, 0), time(10, 30), '优秀代表经验分享', '白云学堂', '四级经理代表分享', '四级经理代表分享个人成长规划', '闫元元'),
    ('2026-07-24', time(10, 40), time(11, 40), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '小CEO代表：如何通过岗位工作提升个人价值', '优秀代表'),
    ('2026-07-24', time(14, 0), time(14, 50), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '如何成长为技术专家', '戴亨玮'),
    ('2026-07-24', time(15, 0), time(15, 50), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '如何成长为技能人才', '吴浅灿'),
    ('2026-07-24', time(16, 0), time(16, 50), '优秀代表经验分享', '白云学堂', '优秀员工代表经验分享', '“从新人到熟手”的心路历程', '李星颖'),
)


# The source key points to the matching row in the former schedule. Rows not
# listed here kept the same date, start time, and title.
SOURCE_OVERRIDES = {
    10: ('2026-07-21', time(15, 0), '网络运营概况'),
    11: ('2026-07-21', time(16, 0), '政企营销概况'),
    13: ('2026-07-21', time(16, 50), '参观'),
    23: ('2026-07-24', time(14, 0), '优秀员工代表经验分享'),
    24: ('2026-07-24', time(14, 40), '优秀员工代表经验分享'),
    25: ('2026-07-24', time(15, 30), '优秀员工代表经验分享'),
    26: ('2026-07-24', time(16, 10), '优秀员工代表经验分享'),
}


OBSOLETE_ROWS = (
    ('2026-07-19', time(19, 0), '晚间活动'),
    ('2026-07-20', time(19, 0), '晚间活动'),
    ('2026-07-22', time(14, 0), '中国电信创新孵化基地'),
    ('2026-07-22', time(19, 0), '晚间活动'),
    ('2026-07-23', time(19, 0), '晚间活动'),
)


SCHEDULE_FINGERPRINT = (
    ('2026-07-19', time(14, 0), '报到'),
    ('2026-07-23', time(9, 0), '劳模精神'),
)


def update_training_schedule(apps, schema_editor):
    TrainingCamp = apps.get_model('api', 'TrainingCamp')
    Course = apps.get_model('api', 'Course')
    schedule_start = date(2026, 7, 19)
    schedule_end = date(2026, 7, 24)

    candidate_camp_ids = None
    for day, start, title in SCHEDULE_FINGERPRINT:
        matching_ids = set(Course.objects.filter(
            date=date.fromisoformat(day),
            start_time=start,
            title=title,
        ).values_list('camp_id', flat=True))
        candidate_camp_ids = matching_ids if candidate_camp_ids is None else candidate_camp_ids & matching_ids

    matching_camps = TrainingCamp.objects.filter(
        pk__in=candidate_camp_ids or set(),
        is_active=True,
        start_date=schedule_start,
        end_date=schedule_end,
    )
    if matching_camps.count() != 1:
        return
    camp = matching_camps.first()

    camp_courses = Course.objects.filter(camp_id=camp.pk)
    used_ids = set()

    for index, row in enumerate(COURSES):
        day, start, end, topic, room, title, content, teacher = row
        target_day = date.fromisoformat(day)
        source_day, source_start, source_title = SOURCE_OVERRIDES.get(
            index,
            (day, start, title),
        )
        course = camp_courses.filter(
            date=target_day,
            start_time=start,
            title=title,
        ).exclude(pk__in=used_ids).order_by('pk').first()
        if course is None:
            course = camp_courses.filter(
                date=date.fromisoformat(source_day),
                start_time=source_start,
                title=source_title,
            ).exclude(pk__in=used_ids).order_by('pk').first()
        if course is None:
            course = Course(camp_id=camp.pk)

        course.date = target_day
        course.start_time = start
        course.end_time = end
        course.topic = topic
        course.room = room
        course.title = title
        course.content = content
        course.teacher = teacher
        course.status = 'upcoming'
        course.sort_order = index
        course.save()
        used_ids.add(course.pk)

    cleanup_rows = set(OBSOLETE_ROWS) | set(SOURCE_OVERRIDES.values())
    for day, start, title in cleanup_rows:
        camp_courses.filter(
            date=date.fromisoformat(day),
            start_time=start,
            title=title,
        ).exclude(pk__in=used_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_course_materials'),
    ]

    operations = [
        migrations.RunPython(update_training_schedule, migrations.RunPython.noop),
    ]
