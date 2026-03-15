from django.db import models
from django.conf import settings


CATEGORY_GENERAL = 'general'
CATEGORY_ENTERTAINMENT = 'entertainment'
CATEGORY_SPORTS = 'sports'
CATEGORY_TECH = 'tech'
CATEGORY_CREATIVE = 'creative'
CATEGORY_INTERESTS = 'interests'

CATEGORY_CHOICES = [
    (CATEGORY_GENERAL, 'Nairaland General'),
    (CATEGORY_ENTERTAINMENT, 'Entertainment'),
    (CATEGORY_SPORTS, 'Sports'),
    (CATEGORY_TECH, 'Technology'),
    (CATEGORY_CREATIVE, 'Creative'),
    (CATEGORY_INTERESTS, 'Interests & Lifestyle'),
]

CATEGORY_META = {
    CATEGORY_GENERAL:       ('Nairaland General',    'fa-solid fa-globe'),
    CATEGORY_ENTERTAINMENT: ('Entertainment',         'fa-solid fa-film'),
    CATEGORY_SPORTS:        ('Sports',               'fa-solid fa-trophy'),
    CATEGORY_TECH:          ('Technology',           'fa-solid fa-microchip'),
    CATEGORY_CREATIVE:      ('Creative',             'fa-solid fa-palette'),
    CATEGORY_INTERESTS:     ('Interests & Lifestyle','fa-solid fa-star'),
}

CATEGORY_ORDER = [
    CATEGORY_GENERAL,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_SPORTS,
    CATEGORY_TECH,
    CATEGORY_CREATIVE,
    CATEGORY_INTERESTS,
]


class Stage(models.Model):
    """
    Stage/Community model for organizing posts.
    Similar to subreddits or forums.
    """
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name="owned_stages"
    )
    title = models.CharField(max_length=200, help_text="Full stage title")
    name = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Short unique name for URL"
    )
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(
        upload_to='stages/', 
        blank=True,
        null=True,
        help_text="Stage cover image"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Membership tracking
    members_count = models.PositiveIntegerField(default=0)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='joined_stages',
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Stage"
        verbose_name_plural = "Stages"
        indexes = [
            # Sidebar: filter active stages, ordered by member count
            models.Index(fields=['is_active', '-members_count']),
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f's/{self.name}'
    
    def save(self, *args, **kwargs):
        """Ensure name is lowercase and URL-friendly."""
        if self.name:
            self.name = self.name.lower().replace(' ', '_')
        super().save(*args, **kwargs)


class StageModerator(models.Model):
    """
    Links a user to a stage as a moderator.
    - is_super_mod=True → can moderate ALL stages (stage field is ignored)
    - is_super_mod=False → moderates only the assigned stage
    Stage admins (stage.admin) have implicit mod powers without needing a record.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='stage_mod_roles',
    )
    # Null when is_super_mod=True (applies to all stages)
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='moderators',
    )
    is_super_mod = models.BooleanField(
        default=False,
        help_text="Super mods can moderate every stage on the platform.",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mods_added',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Stage Moderator"
        verbose_name_plural = "Stage Moderators"

    def __str__(self):
        if self.is_super_mod:
            return f'{self.user.username} (Super Mod — all stages)'
        return f'{self.user.username} → s/{self.stage.name if self.stage else "?"}'


class StageBan(models.Model):
    """A user banned from posting/commenting in a specific stage."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='stage_bans',
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name='banned_users',
    )
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='bans_issued',
    )
    reason = models.TextField(blank=True, max_length=500)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'stage')
        ordering = ['-created_at']
        verbose_name = "Stage Ban"
        verbose_name_plural = "Stage Bans"

    def __str__(self):
        return f'{self.user.username} banned from s/{self.stage.name}'

