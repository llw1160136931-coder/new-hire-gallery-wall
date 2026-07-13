import uuid
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class TrainingCamp(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    submission_starts_at = models.DateTimeField(blank=True, null=True)
    submission_ends_at = models.DateTimeField(blank=True, null=True)
    voting_starts_at = models.DateTimeField(blank=True, null=True)
    voting_ends_at = models.DateTimeField(blank=True, null=True)
    vote_limit = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F('start_date')),
                name='training_camp_end_after_start',
            ),
            models.UniqueConstraint(
                fields=['is_active'],
                condition=Q(is_active=True),
                name='single_active_training_camp',
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors['end_date'] = '结束日期不能早于开始日期'
        for starts_field, ends_field in [
            ('submission_starts_at', 'submission_ends_at'),
            ('voting_starts_at', 'voting_ends_at'),
        ]:
            starts_at = getattr(self, starts_field)
            ends_at = getattr(self, ends_field)
            if starts_at and ends_at and ends_at < starts_at:
                errors[ends_field] = '结束时间不能早于开始时间'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.is_active:
            TrainingCamp.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = 'student', '学员'
        ADMIN = 'admin', '管理员'

    class Gender(models.TextChoices):
        UNKNOWN = 'unknown', '未填写'
        FEMALE = 'female', '女'
        MALE = 'male', '男'
        OTHER = 'other', '其他'

    class Mbti(models.TextChoices):
        INTJ = 'INTJ', 'INTJ'
        INTP = 'INTP', 'INTP'
        ENTJ = 'ENTJ', 'ENTJ'
        ENTP = 'ENTP', 'ENTP'
        INFJ = 'INFJ', 'INFJ'
        INFP = 'INFP', 'INFP'
        ENFJ = 'ENFJ', 'ENFJ'
        ENFP = 'ENFP', 'ENFP'
        ISTJ = 'ISTJ', 'ISTJ'
        ISFJ = 'ISFJ', 'ISFJ'
        ESTJ = 'ESTJ', 'ESTJ'
        ESFJ = 'ESFJ', 'ESFJ'
        ISTP = 'ISTP', 'ISTP'
        ISFP = 'ISFP', 'ISFP'
        ESTP = 'ESTP', 'ESTP'
        ESFP = 'ESFP', 'ESFP'

    class Zodiac(models.TextChoices):
        ARIES = '白羊座', '白羊座'
        TAURUS = '金牛座', '金牛座'
        GEMINI = '双子座', '双子座'
        CANCER = '巨蟹座', '巨蟹座'
        LEO = '狮子座', '狮子座'
        VIRGO = '处女座', '处女座'
        LIBRA = '天秤座', '天秤座'
        SCORPIO = '天蝎座', '天蝎座'
        SAGITTARIUS = '射手座', '射手座'
        CAPRICORN = '摩羯座', '摩羯座'
        AQUARIUS = '水瓶座', '水瓶座'
        PISCES = '双鱼座', '双鱼座'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    name = models.CharField(max_length=50)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    workplace = models.CharField(max_length=100, blank=True)
    mbti = models.CharField(max_length=4, choices=Mbti.choices, blank=True)
    zodiac = models.CharField(max_length=20, choices=Zodiac.choices, blank=True)
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

    camp = models.ForeignKey(TrainingCamp, on_delete=models.PROTECT, related_name='courses')
    title = models.CharField(max_length=120)
    topic = models.CharField(max_length=120, blank=True)
    teacher = models.CharField(max_length=80)
    room = models.CharField(max_length=80)
    content = models.TextField(blank=True)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPCOMING)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['date', 'start_time', 'sort_order']

    def save(self, *args, **kwargs):
        if not self.camp_id:
            self.camp = TrainingCamp.get_active()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.date} {self.title}'


def normalize_tag_name(value):
    return unicodedata.normalize('NFKC', value).strip().lstrip('#').strip().casefold()


class Tag(models.Model):
    name = models.CharField(max_length=20)
    normalized_name = models.CharField(max_length=20, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def clean(self):
        self.name = self.name.strip().lstrip('#').strip()
        if not self.name:
            raise ValidationError({'name': '标签不能为空'})

    def save(self, *args, **kwargs):
        self.clean()
        self.normalized_name = normalize_tag_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Work(models.Model):
    class WorkType(models.TextChoices):
        TRAINING = 'training', '培训作品'
        AI = 'ai', 'AI 作品'

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已发布'
        REJECTED = 'rejected', '已打回'

    class MediaType(models.TextChoices):
        IMAGE = 'image', '图片'
        PDF = 'pdf', 'PDF'
        VIDEO = 'video', '视频'
        LINK = 'link', '链接'

    camp = models.ForeignKey(TrainingCamp, on_delete=models.PROTECT, related_name='works')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='works')
    title = models.CharField(max_length=120)
    work_type = models.CharField(max_length=20, choices=WorkType.choices)
    image = models.ImageField(upload_to='works/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    attachment = models.FileField(upload_to='works/files/', blank=True, null=True)
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.IMAGE)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    link = models.URLField(blank=True)
    description = models.TextField()
    tags = models.ManyToManyField(Tag, related_name='works', blank=True)
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

    def save(self, *args, **kwargs):
        if not self.camp_id:
            self.camp = TrainingCamp.get_active()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class WorkImage(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='works/gallery/')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['work', 'order'], name='unique_work_image_order'),
        ]

    def __str__(self):
        return f'{self.work_id}:{self.order}'


class WorkReviewLog(models.Model):
    class Action(models.TextChoices):
        APPROVE = 'approve', '通过'
        REJECT = 'reject', '打回'

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='review_logs')
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='work_review_logs',
        blank=True,
        null=True,
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.work_id}:{self.action}'


class ChunkedUpload(models.Model):
    class Status(models.TextChoices):
        UPLOADING = 'uploading', '上传中'
        COMPLETED = 'completed', '已完成'
        CONSUMED = 'consumed', '已使用'

    upload_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    camp = models.ForeignKey(TrainingCamp, on_delete=models.PROTECT, related_name='uploads')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chunked_uploads')
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    media_type = models.CharField(max_length=20, choices=Work.MediaType.choices)
    total_size = models.PositiveBigIntegerField()
    total_chunks = models.PositiveIntegerField()
    uploaded_chunks = models.JSONField(default=list)
    file = models.FileField(upload_to='works/files/', blank=True, null=True)
    expected_sha256 = models.CharField(max_length=64, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.file_name} ({self.status})'


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
