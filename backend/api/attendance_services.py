from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    AttendanceAuditLog,
    AttendanceRecord,
    AttendanceSession,
    Profile,
    TrainingCamp,
    TrainingCampMembership,
)


class AttendanceServiceError(Exception):
    def __init__(self, detail, *, status_code=400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def normalized_reason(value):
    reason = str(value or '').strip()
    if len(reason) < 5 or len(reason) > 200:
        raise AttendanceServiceError('原因长度必须为 5-200 个字符')
    return reason


def is_camp_member(user, camp):
    return TrainingCampMembership.objects.filter(camp=camp, student=user).exists()


def session_has_ended(session, now):
    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    _, ends_at = AttendanceSession.window_for_slot(session.time_slot)
    return session.date < local_now.date() or (
        session.date == local_now.date() and local_now.time() >= ends_at
    )


def _display_name(user):
    profile = getattr(user, 'profile', None)
    return profile.name if profile else ''


def _require_attendance_admin(actor):
    if (
        not actor
        or not actor.is_authenticated
        or not actor.is_active
        or getattr(getattr(actor, 'profile', None), 'role', None) != Profile.Role.ADMIN
    ):
        raise AttendanceServiceError('只有管理员可以执行此操作', status_code=403)


def _write_audit(record, action, actor, reason):
    return AttendanceAuditLog.objects.create(
        record=record,
        action=action,
        actor=actor,
        reason=reason,
        actor_username=actor.username,
        actor_name=_display_name(actor),
        student_username=record.student.username,
        student_name=_display_name(record.student),
        camp_id_snapshot=record.session.camp_id,
        session_date=record.session.date,
        time_slot=record.session.time_slot,
    )


def grant_makeup(*, session_id, student_id, reason, actor, now=None):
    _require_attendance_admin(actor)
    reason = normalized_reason(reason)
    now = now or timezone.now()
    camp = TrainingCamp.get_active()
    if not camp:
        raise AttendanceServiceError('当前没有激活的培训期', status_code=404)

    session = AttendanceSession.objects.filter(pk=session_id).first()
    if not session:
        raise AttendanceServiceError('签到场次不存在', status_code=404)
    if session.camp_id != camp.id:
        raise AttendanceServiceError('只能处理当前培训期的签到场次')
    if not camp.start_date <= session.date <= camp.end_date:
        raise AttendanceServiceError('签到场次不在当前培训期日期范围内')
    if not session_has_ended(session, now):
        raise AttendanceServiceError('只能为已经结束的签到时段补签')

    user_model = get_user_model()
    with transaction.atomic():
        student = (
            user_model.objects.select_for_update()
            .filter(pk=student_id)
            .first()
        )
        student_role = (
            Profile.objects.filter(user_id=student.id)
            .values_list('role', flat=True)
            .first()
            if student
            else None
        )
        if (
            not student
            or not student.is_active
            or student.is_staff
            or student.is_superuser
            or student_role != Profile.Role.STUDENT
        ):
            raise AttendanceServiceError('补签对象必须是当前启用的学员')
        if not is_camp_member(student, camp):
            raise AttendanceServiceError('该学员不属于当前培训期')

        record = (
            AttendanceRecord.objects.select_for_update()
            .filter(session=session, student=student)
            .first()
        )
        if record and record.status == AttendanceRecord.Status.ACTIVE:
            raise AttendanceServiceError('该学员本时段已经签到', status_code=409)
        if record and record.source != AttendanceRecord.Source.ADMIN_MAKEUP:
            raise AttendanceServiceError('已有正常签到记录，不能改为管理员补签', status_code=409)

        reactivated = record is not None
        if record:
            record.source = AttendanceRecord.Source.ADMIN_MAKEUP
            record.recorded_by = actor
            record.makeup_reason = reason
            record.status = AttendanceRecord.Status.ACTIVE
            record.signed_at = now
            record.revoked_by = None
            record.revoked_at = None
            record.revoke_reason = ''
            record.save(update_fields=[
                'source',
                'recorded_by',
                'makeup_reason',
                'status',
                'signed_at',
                'revoked_by',
                'revoked_at',
                'revoke_reason',
            ])
        else:
            try:
                with transaction.atomic():
                    record = AttendanceRecord.objects.create(
                        session=session,
                        student=student,
                        source=AttendanceRecord.Source.ADMIN_MAKEUP,
                        recorded_by=actor,
                        makeup_reason=reason,
                    )
                    AttendanceRecord.objects.filter(pk=record.pk).update(signed_at=now)
                    record.signed_at = now
            except IntegrityError as exc:
                raise AttendanceServiceError('该学员本时段已经签到', status_code=409) from exc
        record.session = session
        record.student = student

        _write_audit(record, AttendanceAuditLog.Action.GRANT, actor, reason)
        return record, reactivated


def revoke_makeup(*, record_id, reason, actor, now=None):
    _require_attendance_admin(actor)
    reason = normalized_reason(reason)
    now = now or timezone.now()
    camp = TrainingCamp.get_active()
    if not camp:
        raise AttendanceServiceError('当前没有激活的培训期', status_code=404)

    record_ids = (
        AttendanceRecord.objects.filter(pk=record_id)
        .values('student_id', 'session_id')
        .first()
    )
    if not record_ids:
        raise AttendanceServiceError('签到记录不存在', status_code=404)
    session = AttendanceSession.objects.filter(pk=record_ids['session_id']).first()
    if not session:
        raise AttendanceServiceError('签到场次不存在', status_code=404)

    user_model = get_user_model()
    with transaction.atomic():
        student = (
            user_model.objects.select_for_update()
            .filter(pk=record_ids['student_id'])
            .first()
        )
        if not student:
            raise AttendanceServiceError('签到学员不存在', status_code=404)
        record = AttendanceRecord.objects.select_for_update().filter(pk=record_id).first()
        if not record:
            raise AttendanceServiceError('签到记录不存在', status_code=404)
        if record.student_id != student.id or record.session_id != session.id:
            raise AttendanceServiceError('签到记录已发生变化，请刷新后重试', status_code=409)
        if session.camp_id != camp.id:
            raise AttendanceServiceError('只能处理当前培训期的签到记录')
        if record.source != AttendanceRecord.Source.ADMIN_MAKEUP:
            raise AttendanceServiceError('正常签到记录不能通过补签功能撤销')
        if record.status != AttendanceRecord.Status.ACTIVE:
            raise AttendanceServiceError('该补签记录已经撤销', status_code=409)

        record.status = AttendanceRecord.Status.REVOKED
        record.revoked_by = actor
        record.revoked_at = now
        record.revoke_reason = reason
        record.save(update_fields=['status', 'revoked_by', 'revoked_at', 'revoke_reason'])
        record.session = session
        record.student = student
        _write_audit(record, AttendanceAuditLog.Action.REVOKE, actor, reason)
        return record
