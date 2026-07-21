import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_attendance_makeup_data(apps, schema_editor):
    AttendanceRecord = apps.get_model('api', 'AttendanceRecord')
    TrainingCamp = apps.get_model('api', 'TrainingCamp')
    TrainingCampMembership = apps.get_model('api', 'TrainingCampMembership')
    Profile = apps.get_model('api', 'Profile')

    AttendanceRecord.objects.update(
        source='code',
        recorded_by=None,
        makeup_reason='',
        status='active',
        revoked_by=None,
        revoked_at=None,
        revoke_reason='',
    )

    camp = TrainingCamp.objects.filter(is_active=True).first()
    if not camp:
        return

    student_ids = Profile.objects.filter(
        role='student',
        user__is_active=True,
        user__is_staff=False,
        user__is_superuser=False,
    ).values_list('user_id', flat=True)
    TrainingCampMembership.objects.bulk_create(
        [
            TrainingCampMembership(camp_id=camp.id, student_id=student_id)
            for student_id in student_ids
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_profile_training_group'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TrainingCampMembership',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'camp',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='memberships',
                        to='api.trainingcamp',
                    ),
                ),
                (
                    'student',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='training_camp_memberships',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['camp_id', 'student_id'],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('camp', 'student'),
                        name='unique_training_camp_membership',
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='source',
            field=models.CharField(
                choices=[('code', '正常签到'), ('admin_makeup', '管理员补签')],
                db_default='code',
                default='code',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='recorded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recorded_attendance_makeups',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='makeup_reason',
            field=models.CharField(blank=True, db_default='', default='', max_length=200),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='status',
            field=models.CharField(
                choices=[('active', '有效'), ('revoked', '已撤销')],
                db_default='active',
                default='active',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='revoked_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='revoked_attendance_makeups',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='revoke_reason',
            field=models.CharField(blank=True, db_default='', default='', max_length=200),
        ),
        migrations.RunPython(
            backfill_attendance_makeup_data,
            migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name='AttendanceAuditLog',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'action',
                    models.CharField(
                        choices=[('grant', '管理员补签'), ('revoke', '撤销补签')],
                        max_length=20,
                    ),
                ),
                ('reason', models.CharField(max_length=200)),
                ('actor_username', models.CharField(max_length=150)),
                ('actor_name', models.CharField(blank=True, max_length=50)),
                ('student_username', models.CharField(max_length=150)),
                ('student_name', models.CharField(max_length=50)),
                ('camp_id_snapshot', models.PositiveBigIntegerField()),
                ('session_date', models.DateField()),
                (
                    'time_slot',
                    models.CharField(
                        choices=[
                            ('morning', '上午签到'),
                            ('afternoon', '下午签到'),
                            ('evening', '晚间签到'),
                        ],
                        max_length=20,
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'actor',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='attendance_audit_logs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'record',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='audit_logs',
                        to='api.attendancerecord',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='attendancerecord',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        source='code',
                        recorded_by__isnull=True,
                        makeup_reason='',
                    )
                    | (
                        models.Q(source='admin_makeup', recorded_by__isnull=False)
                        & ~models.Q(makeup_reason='')
                    )
                ),
                name='attendance_record_source_fields_valid',
            ),
        ),
        migrations.AddConstraint(
            model_name='attendancerecord',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status='active',
                        revoked_by__isnull=True,
                        revoked_at__isnull=True,
                        revoke_reason='',
                    )
                    | (
                        models.Q(
                            status='revoked',
                            source='admin_makeup',
                            revoked_by__isnull=False,
                            revoked_at__isnull=False,
                        )
                        & ~models.Q(revoke_reason='')
                    )
                ),
                name='attendance_record_status_fields_valid',
            ),
        ),
    ]
