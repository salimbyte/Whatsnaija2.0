from django.db import models
from django.conf import settings

from posts.models import Post


class Comment(models.Model):
    """
    Comments on posts with support for anonymous comments and replies.
    """
    post = models.ForeignKey(
        Post, 
        default=None, 
        null=True, 
        on_delete=models.CASCADE, 
        related_name="comments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        default=None, 
        null=True, 
        on_delete=models.SET_NULL,
        related_name="comments"
    )
    is_anon = models.BooleanField(default=False, help_text="Is this comment anonymous?")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Optional single image / GIF attachment
    image = models.ImageField(
        upload_to='comment_media/',
        null=True,
        blank=True,
        help_text="One image or GIF per comment (max 5 MB)."
    )
    gif_url = models.URLField(
        blank=True,
        default='',
        help_text="Tenor GIF URL (used when a GIF is picked instead of uploaded)."
    )

    # Support for nested comments (replies)
    reply_to = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        related_name="replies", 
        blank=True,
        null=True, 
        default=None
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Comment"
        verbose_name_plural = "Comments"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['post']),
            # Top-level comment queries (reply_to IS NULL filter)
            models.Index(fields=['post', 'reply_to', '-created_at']),
            # Reply thread queries
            models.Index(fields=['reply_to', 'created_at']),
        ]
    
    def __str__(self):
        username = "Anonymous" if self.is_anon or self.user is None else self.user.username
        post_title = self.post.title if self.post else "Deleted Post"
        return f'Comment on "{post_title}" by {username}'
    
    @property
    def total_likes(self):
        """Return the count of likes for this comment."""
        return self.commentlikes.count()

    @property
    def total_dislikes(self):
        """Return the count of dislikes for this comment."""
        return self.commentdislikes.count()

    @property
    def ordered_replies(self):
        """Direct replies in chronological order (oldest first)."""
        return self.replies.order_by('created_at')


class CommentLike(models.Model):
    """
    Likes for comments.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="liked_comments"
    )
    comment = models.ForeignKey(
        Comment, 
        on_delete=models.CASCADE, 
        related_name="commentlikes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')
        verbose_name = "Comment Like"
        verbose_name_plural = "Comment Likes"

    def __str__(self):
        return f"{self.user.username} liked comment #{self.comment.id}"


class CommentDislike(models.Model):
    """
    Dislikes for comments.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="disliked_comments"
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="commentdislikes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')
        verbose_name = "Comment Dislike"
        verbose_name_plural = "Comment Dislikes"

    def __str__(self):
        return f"{self.user.username} disliked comment #{self.comment.id}"


REACTION_EMOJIS = ['🔥', '💯', '😂', '🤔']


class CommentReaction(models.Model):
    """One emoji reaction per (comment, user, emoji) triple."""
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_reactions'
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user', 'emoji')
        verbose_name = 'Comment Reaction'
        verbose_name_plural = 'Comment Reactions'

    def __str__(self):
        return f"{self.user.username} reacted {self.emoji} to comment #{self.comment.id}"