import datetime

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q
from django.utils import timezone


def assign_existing_data(apps, schema_editor):
    TrainingCamp = apps.get_model('api', 'TrainingCamp')
    Course = apps.get_model('api', 'Course')
    Work = apps.get_model('api', 'Work')
    ChunkedUpload = apps.get_model('api', 'ChunkedUpload')

    first_course = Course.objects.order_by('date').first()
    last_course = Course.objects.order_by('-date').first()
    today = timezone.localdate()
    camp = TrainingCamp.objects.create(
        name='新员工训练营',
        slug='default-training-camp',
        start_date=first_course.date if first_course else today,
        end_date=last_course.date if last_course else today,
        vote_limit=5,
        is_active=True,
    )
    Course.objects.filter(camp__isnull=True).update(camp=camp)
    Work.objects.filter(camp__isnull=True).update(camp=camp)
    for upload in ChunkedUpload.objects.filter(camp__isnull=True):
        upload.camp = camp
        upload.expires_at = upload.created_at + datetime.timedelta(hours=24)
        upload.save(update_fields=['camp', 'expires_at'])


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0005_workreviewlog'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrainingCamp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(max_length=80, unique=True)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('submission_starts_at', models.DateTimeField(blank=True, null=True)),
                ('submission_ends_at', models.DateTimeField(blank=True, null=True)),
                ('voting_starts_at', models.DateTimeField(blank=True, null=True)),
                ('voting_ends_at', models.DateTimeField(blank=True, null=True)),
                ('vote_limit', models.PositiveSmallIntegerField(default=5)),
                ('is_active', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-start_date', '-id']},
        ),
        migrations.AddField(
            model_name='course',
            name='camp',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='courses', to='api.trainingcamp'),
        ),
        migrations.AddField(
            model_name='work',
            name='camp',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='works', to='api.trainingcamp'),
        ),
        migrations.AddField(
            model_name='chunkedupload',
            name='camp',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='uploads', to='api.trainingcamp'),
        ),
        migrations.AddField(
            model_name='chunkedupload',
            name='consumed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chunkedupload',
            name='expected_sha256',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='chunkedupload',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chunkedupload',
            name='sha256',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='chunkedupload',
            name='status',
            field=models.CharField(choices=[('uploading', '上传中'), ('completed', '已完成'), ('consumed', '已使用')], default='uploading', max_length=20),
        ),
        migrations.RunPython(assign_existing_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='course',
            name='camp',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='courses', to='api.trainingcamp'),
        ),
        migrations.AlterField(
            model_name='work',
            name='camp',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='works', to='api.trainingcamp'),
        ),
        migrations.AlterField(
            model_name='chunkedupload',
            name='camp',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploads', to='api.trainingcamp'),
        ),
        migrations.AlterField(
            model_name='chunkedupload',
            name='expires_at',
            field=models.DateTimeField(),
        ),
        migrations.AddConstraint(
            model_name='trainingcamp',
            constraint=models.CheckConstraint(condition=Q(end_date__gte=F('start_date')), name='training_camp_end_after_start'),
        ),
        migrations.AddConstraint(
            model_name='trainingcamp',
            constraint=models.UniqueConstraint(condition=Q(is_active=True), fields=('is_active',), name='single_active_training_camp'),
        ),
    ]
