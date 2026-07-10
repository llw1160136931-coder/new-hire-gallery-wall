import unicodedata

from django.db import migrations, models


def normalize(value):
    return unicodedata.normalize('NFKC', value).strip().lstrip('#').strip().casefold()


def backfill_demo_tags(apps, schema_editor):
    Tag = apps.get_model('api', 'Tag')
    Work = apps.get_model('api', 'Work')
    tag_by_title = {
        'AI 入职欢迎海报': ['AI 海报'],
        '培训流程小程序原型': ['流程 Demo'],
        '部门知识地图': ['知识地图'],
    }
    for title, names in tag_by_title.items():
        for work in Work.objects.filter(title=title):
            for name in names:
                tag, _ = Tag.objects.get_or_create(
                    normalized_name=normalize(name),
                    defaults={'name': name},
                )
                work.tags.add(tag)


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0006_training_camps_and_upload_security'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=20)),
                ('normalized_name', models.CharField(editable=False, max_length=20, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='work',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='works', to='api.tag'),
        ),
        migrations.RunPython(backfill_demo_tags, migrations.RunPython.noop),
    ]
