from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = 'student', '学员'
        ADMIN = 'admin', '管理员'

    class Gender(models.TextChoices):
        UNKNOWN = 'unknown', '未填写'
        FEMALE = 'female', '女'
        MALE = 'male', '男'
        OTHER = 'other', '其他'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    name = models.CharField(max_length=50)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    school = models.CharField(max_length=100, blank=True)
    mbti = models.CharField(max_length=4, blank=True)
    zodiac = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.UNKNOWN)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Course(models.Model):
    class Status(models.TextChoices):
        DONE = 'done', '已结束'
        LIVE = 'live', '进行中'
        UPCOMING = 'upcoming', '未开始'

    title = models.CharField(max_length=120)
    teacher = models.CharField(max_length=80)
    room = models.CharField(max_length=80)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPCOMING)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['date', 'start_time', 'sort_order']

    def __str__(self):
        return f'{self.date} {self.title}'


class Work(models.Model):
    class WorkType(models.TextChoices):
        TRAINING = 'training', '培训作品'
        AI = 'ai', 'AI 作品'

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已发布'
        REJECTED = 'rejected', '已打回'

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='works')
    title = models.CharField(max_length=120)
    work_type = models.CharField(max_length=20, choices=WorkType.choices)
    image = models.ImageField(upload_to='works/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    link = models.URLField(blank=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='reviewed_works',
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'work'], name='unique_user_work_like'),
        ]


class Vote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='votes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'work'], name='unique_user_work_vote'),
        ]

# Create your models here.
