import api.storage
import api.talent_profile_files
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_alter_work_work_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TalentProfileReport',
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
                    'file',
                    models.FileField(
                        storage=api.storage.ProtectedCourseStorage(),
                        upload_to=api.talent_profile_files.talent_profile_report_upload_to,
                    ),
                ),
                ('original_filename', models.CharField(max_length=255)),
                ('file_size', models.PositiveBigIntegerField()),
                ('sha256', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'camp',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='talent_profile_reports',
                        to='api.trainingcamp',
                    ),
                ),
                (
                    'student',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='talent_profile_reports',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['camp_id', 'student_id'],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('camp', 'student'),
                        name='unique_talent_profile_per_camp_student',
                    ),
                ],
            },
        ),
    ]
