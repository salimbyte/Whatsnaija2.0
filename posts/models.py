from django.db import models, IntegrityError
from django.utils.text import slugify
from ckeditor_uploader.fields import RichTextUploadingField

from users.models import User
from stages.models import Stage


class Post(models.Model):
    """
    Main Post model for user-generated content.
    """
    title = models.CharField(max_length=240)
    slug = models.SlugField(
        max_length=100, 
        null=True, 
        blank=True, 
        unique=True
    )
    body = RichTextUploadingField(blank=True)
    author = models.ForeignKey(
        User, 
        default=None, 
        null=True, 
        on_delete=models.SET_NULL, 
        related_name="posts"
    )
    stage = models.ForeignKey(
        Stage, 
        default=None, 
        null=True, 
        on_delete=models.SET_NULL,
        related_name="posts"
    )
    url = models.URLField("URL", max_length=256, blank=True)

    # OG image scraped from the submitted URL in the background after post creation
    og_image = models.URLField("OG Image URL", max_length=1024, blank=True, default='')
    
    # Timestamps (fixed: created_at should use auto_now_add, not auto_now)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date Created')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date Updated')
    
    # Status flags
    is_published = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)

    # View tracking
    view_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Post"
        verbose_name_plural = "Posts"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['slug']),
            # Most common filter: only published, non-blocked posts are shown
            models.Index(fields=['is_published', 'is_blocked']),
            # Stage feed queries
            models.Index(fields=['stage', 'is_published', 'is_blocked', '-created_at']),
            # Author profile page
            models.Index(fields=['author', 'is_published', '-created_at']),
        ]
    
    def __str__(self):
        return f'{self.title} - {self.stage if self.stage else "No Stage"}'
    
    def save(self, *args, **kwargs):
        """Auto-generate slug from title if not provided."""
        if not self.slug:
            base = slugify(self.title) or "post"
            max_length = self._meta.get_field('slug').max_length
            base = base[:max_length].strip('-') or "post"

            for counter in range(0, 1000):
                if counter == 0:
                    candidate = base
                else:
                    suffix = f"-{counter}"
                    cut = max_length - len(suffix)
                    candidate = f"{base[:cut].rstrip('-')}{suffix}"

                if Post.objects.filter(slug=candidate).exists():
                    continue
                self.slug = candidate
                try:
                    return super().save(*args, **kwargs)
                except IntegrityError:
                    # Handle race: another row may have taken this slug.
                    self.slug = None
                    continue
            raise RuntimeError("Could not generate a unique slug for this post.")
        return super().save(*args, **kwargs)
    
    @property
    def total_likes(self):
        """Return the count of likes for this post."""
        return self.likes.count()
    
    @property
    def total_dislikes(self):
        """Return the count of dislikes for this post."""
        return self.dislikes.count()
    
    @property
    def total_comments(self):
        """Return the count of comments for this post."""
        return self.comments.count()


class Like(models.Model):
    """
    Likes for posts.
    """
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="liked_posts"
    )
    post = models.ForeignKey(
        Post, 
        on_delete=models.CASCADE, 
        related_name="likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        verbose_name = "Like"
        verbose_name_plural = "Likes"
        indexes = [
            models.Index(fields=['post']),
            models.Index(fields=['user', 'post']),
        ]

    def __str__(self):
        return f"{self.user.username} liked {self.post.title}"


class DisLike(models.Model):
    """
    Dislikes for posts.
    """
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="disliked_posts"
    )
    post = models.ForeignKey(
        Post, 
        on_delete=models.CASCADE, 
        related_name="dislikes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        verbose_name = "Dislike"
        verbose_name_plural = "Dislikes"
        indexes = [
            models.Index(fields=['post']),
            models.Index(fields=['user', 'post']),
        ]

    def __str__(self):
        return f"{self.user.username} disliked {self.post.title}"


class PostImage(models.Model):
    """
    Images attached to posts.
    """
    post = models.ForeignKey(
        Post, 
        default=None, 
        null=True, 
        related_name="images", 
        on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to='post_media/', null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Post Image"
        verbose_name_plural = "Post Images"
        ordering = ['uploaded_at']

    def __str__(self):
        return f"Image for {self.post.title if self.post else 'Deleted Post'}"


class Bookmark(models.Model):
    """User bookmarks / saved posts."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['post']),
        ]

    def __str__(self):
        return f'{self.user.username} bookmarked {self.post.title}'
