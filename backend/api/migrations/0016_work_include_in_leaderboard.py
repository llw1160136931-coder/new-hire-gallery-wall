from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_attendance_makeup'),
    ]

    operations = [
        migrations.AddField(
            model_name='work',
            name='include_in_leaderboard',
            field=models.BooleanField(
                default=True,
                help_text='关闭后作品仍在作品墙展示，但不会进入排行榜或本周精选。',
                verbose_name='参与排行榜',
            ),
        ),
    ]
