from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0007_real_work_tags'),
    ]

    operations = [
        migrations.RenameField(
            model_name='profile',
            old_name='school',
            new_name='workplace',
        ),
        migrations.AlterField(
            model_name='profile',
            name='mbti',
            field=models.CharField(
                blank=True,
                choices=[
                    ('INTJ', 'INTJ'), ('INTP', 'INTP'), ('ENTJ', 'ENTJ'), ('ENTP', 'ENTP'),
                    ('INFJ', 'INFJ'), ('INFP', 'INFP'), ('ENFJ', 'ENFJ'), ('ENFP', 'ENFP'),
                    ('ISTJ', 'ISTJ'), ('ISFJ', 'ISFJ'), ('ESTJ', 'ESTJ'), ('ESFJ', 'ESFJ'),
                    ('ISTP', 'ISTP'), ('ISFP', 'ISFP'), ('ESTP', 'ESTP'), ('ESFP', 'ESFP'),
                ],
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name='profile',
            name='zodiac',
            field=models.CharField(
                blank=True,
                choices=[
                    ('白羊座', '白羊座'), ('金牛座', '金牛座'), ('双子座', '双子座'), ('巨蟹座', '巨蟹座'),
                    ('狮子座', '狮子座'), ('处女座', '处女座'), ('天秤座', '天秤座'), ('天蝎座', '天蝎座'),
                    ('射手座', '射手座'), ('摩羯座', '摩羯座'), ('水瓶座', '水瓶座'), ('双鱼座', '双鱼座'),
                ],
                max_length=20,
            ),
        ),
    ]
