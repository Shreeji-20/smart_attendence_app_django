from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    DEPARTMENT_CHOICES = [
        ('CSE', 'Computer Science'),
        ('ECE', 'Electronics & Communication'),
        ('ME', 'Mechanical Engineering'),
        ('CE', 'Civil Engineering'),
        ('EE', 'Electrical Engineering'),
    ]

    SECTION_CHOICES = [
        ('A', 'Section A'),
        ('B', 'Section B'),
        ('C', 'Section C'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    enrollment_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES, null=True, blank=True)
    semester = models.IntegerField(null=True, blank=True)
    section = models.CharField(max_length=1, choices=SECTION_CHOICES, null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    user_class = models.IntegerField(null=True, blank=True)  # For face recognition

    def __str__(self):
        return f"{self.user.username}'s Profile"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)

class Attendance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Present')  # Present, Late, Absent

    class Meta:
        unique_together = ['user', 'date']

    def __str__(self):
        return f"{self.user.username} - {self.date}"

class LeaveRequest(models.Model):
    LEAVE_CHOICES = [
        ('Sick Leave', 'Sick Leave'),
        ('Casual Leave', 'Casual Leave'),
        ('Earned Leave', 'Earned Leave'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=50, choices=LEAVE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, default='Pending')  # Pending, Approved, Rejected

    def __str__(self):
        return f"{self.user.username} - {self.leave_type} ({self.status})"

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('attendance', 'Attendance'),
        ('leave', 'Leave'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"

class Settings(models.Model):
    working_hours_start = models.TimeField()
    working_hours_end = models.TimeField()
    allow_late_checkin = models.BooleanField(default=False)
    late_threshold = models.IntegerField(default=15)  # minutes
    send_notifications = models.BooleanField(default=True)
    max_leaves = models.IntegerField(default=2)
    leave_notice_days = models.IntegerField(default=1)

    class Meta:
        verbose_name = 'Settings'
        verbose_name_plural = 'Settings'

    @classmethod
    def get_settings(cls):
        settings = cls.objects.first()
        if not settings:
            settings = cls.objects.create(
                working_hours_start='09:00',
                working_hours_end='17:00',
                allow_late_checkin=False,
                late_threshold=15,
                send_notifications=True,
                max_leaves=2,
                leave_notice_days=1
            )
        return settings
    

