from django.db import models
from django.conf import settings

from posts.models import Post
from comments.models import Comment
from stages.models import Stage


class Report(models.Model):
    """Reports submitted by users for posts or comments."""
    REPORT_TYPE_CHOICES = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('hate_speech', 'Hate Speech'),
        ('misinformation', 'Misinformation'),
        ('nsfw', 'NSFW Content'),
        ('appeal', 'Appeal'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('action_taken', 'Action Taken'),
        ('dismissed', 'Dismissed'),
    ]
    CONTENT_TYPE_CHOICES = [
        ('post', 'Post'),
        ('comment', 'Comment'),
        ('appeal', 'Appeal'),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_filed'
    )
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES)
    post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    description = models.TextField(blank=True, max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    public_reason = models.CharField(blank=True, max_length=200)
    staff_only = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports_reviewed'
    )
    mod_note = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Mod queue: pending reports per stage
            models.Index(fields=['status']),
            models.Index(fields=['post', 'status']),
        ]

    def __str__(self):
        if self.post:
            target = self.post.title
        elif self.comment_id:
            target = f'Comment #{self.comment_id}'
        else:
            target = 'Appeal'
        return f'Report: {self.report_type} on {target}'


class ModAction(models.Model):
    """Log of moderator actions for audit trail."""
    ACTION_CHOICES = [
        ('block_post', 'Block Post'),
        ('unblock_post', 'Unblock Post'),
        ('delete_post', 'Delete Post'),
        ('delete_comment', 'Delete Comment'),
        ('ban_user', 'Site Ban User'),
        ('unban_user', 'Site Unban User'),
        ('dismiss_report', 'Dismiss Report'),
        ('resolve_report', 'Resolve Report'),
        ('stage_ban', 'Stage Ban User'),
        ('stage_unban', 'Stage Unban User'),
        ('add_mod', 'Add Stage Moderator'),
        ('remove_mod', 'Remove Stage Moderator'),
        ('add_super_mod', 'Add Super Moderator'),
        ('remove_super_mod', 'Remove Super Moderator'),
        ('disable_stage', 'Disable Stage'),
        ('enable_stage', 'Enable Stage'),
    ]

    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mod_actions'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_actions_received'
    )
    target_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    target_comment = models.ForeignKey(
        Comment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    # Stage context for stage-scoped actions
    stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mod_actions',
    )
    reason = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.moderator.username}: {self.get_action_display()}'
