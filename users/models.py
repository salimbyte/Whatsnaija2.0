from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


USERNAME_MAX_LENGTH = 30


class User(AbstractUser):
    """
    Custom User Model extending Django's AbstractUser.
    """
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    # Extra fields beyond Django's default AbstractUser
    gender = models.CharField(
        max_length=1, 
        choices=GENDER_CHOICES, 
        blank=True, 
        null=True
    )
    course = models.CharField(max_length=100, blank=True, null=True)
    stage = models.CharField(max_length=100, blank=True, null=True)

    # Verification-related fields (fixed typo: varified -> verified)
    is_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    # Platform-wide ban expiry (null = permanent when inactive)
    ban_until = models.DateTimeField(blank=True, null=True, db_index=True)

    # Override date_joined for default
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ['-date_joined']

    def __str__(self):
        return self.username


class ReservedUsername(models.Model):
    """Usernames reserved for brands, staff, or platform use."""
    name = models.CharField(max_length=150)
    name_lower = models.CharField(max_length=150, unique=True, editable=False, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name_lower']
        verbose_name = "Reserved Username"
        verbose_name_plural = "Reserved Usernames"

    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        self.name_lower = self.name.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


def is_reserved_username(username: str) -> bool:
    if not username:
        return False
    name = username.strip().lower()
    if not name:
        return False
    return ReservedUsername.objects.filter(name_lower=name).exists()


class UserProfile(models.Model):
    """
    Extended User Profile with additional user information.
    """
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="profile"
    )
    avatar = models.ImageField(
        upload_to="avatars/", 
        blank=True, 
        null=True,
        help_text="User profile picture"
    )
    banner = models.ImageField(
        upload_to="banners/",
        blank=True,
        null=True,
        help_text="Profile banner image"
    )
    bio = models.TextField(
        blank=True, 
        null=True,
        max_length=500,
        help_text="Short bio about the user"
    )
    location = models.CharField(max_length=255, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    profile_views = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(blank=True, null=True)
    total_time_online = models.PositiveIntegerField(default=0, help_text="Total seconds spent online")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def is_online(self):
        """User is online if last_seen within the last 5 minutes."""
        if not self.last_seen:
            return False
        return (timezone.now() - self.last_seen).total_seconds() < 300

    @property
    def online_status(self):
        """
        Returns 'online', 'away', 'offline', or 'never'.
        online  = active within 5 minutes
        away    = active within 30 minutes
        offline = seen before, but more than 30 min ago
        never   = never seen at all
        """
        if not self.last_seen:
            return 'never'
        delta = (timezone.now() - self.last_seen).total_seconds()
        if delta < 300:
            return 'online'
        elif delta < 1800:
            return 'away'
        return 'offline'

    @property
    def time_online_display(self):
        """Human-readable total time spent online."""
        total_seconds = self.total_time_online
        if total_seconds < 60:
            return 'less than a minute'
        if total_seconds < 3600:
            minutes = total_seconds // 60
            return f'{minutes} minute{"s" if minutes != 1 else ""}'
        if total_seconds < 86400:
            hours = total_seconds // 3600
            return f'{hours} hour{"s" if hours != 1 else ""}'
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        if hours:
            return f'{days} day{"s" if days != 1 else ""}, {hours} hr{"s" if hours != 1 else ""}'
        return f'{days} day{"s" if days != 1 else ""}'

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a UserProfile when a User is created.
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save the UserProfile when User is saved.
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()


class Follow(models.Model):
    """User follow relationship."""
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='following'
    )
    following = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='followers'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'following')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['follower']),
            models.Index(fields=['following']),
        ]

    def __str__(self):
        return f'{self.follower.username} follows {self.following.username}'


class Message(models.Model):
    """Direct messages between users."""
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    body = models.TextField(max_length=2000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            # Inbox query: all messages for a user, most recent first
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
            # Unread count query
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f'{self.sender.username} → {self.recipient.username}'


class Notification(models.Model):
    """User notifications for various events."""
    NOTIFICATION_TYPES = [
        ('like', 'Post Liked'),
        ('comment', 'New Comment'),
        ('reply', 'Comment Reply'),
        ('follow', 'New Follower'),
        ('message', 'New Message'),
        ('mention', 'Mentioned'),
        ('mod_add', 'Added as Moderator'),
        ('mod_remove', 'Removed as Moderator'),
        ('stage_ban', 'Stage Banned'),
        ('stage_unban', 'Stage Unbanned'),
        ('post_removed', 'Post Removed by Mod'),
        ('mod_warn', 'Warning from Moderator'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    text = models.CharField(max_length=255)
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Notification bell: fetch unread notifications per user
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f'{self.notification_type}: {self.text}'


class MessageReaction(models.Model):
    """❤️ reaction on a direct message."""
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    reactor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='message_reactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'reactor')

    def __str__(self):
        return f'{self.reactor.username} ❤️ msg#{self.message.pk}'
