from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_work_include_in_leaderboard'),
    ]

    operations = [
        migrations.AlterField(
            model_name='work',
            name='work_type',
            field=models.CharField(
                choices=[
                    ('training', '培训作品'),
                    ('ai', 'AI 作品'),
                    ('ai_competition', 'AI 比赛作品'),
                ],
                max_length=20,
            ),
        ),
    ]
