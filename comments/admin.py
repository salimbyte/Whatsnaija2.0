from django.contrib import admin
from django import forms
from .models import Comment, CommentLike, CommentDislike, CommentReaction


class CommentLikeForm(forms.ModelForm):
    def clean(self):
        user = self.cleaned_data.get('user')
        comment = self.cleaned_data.get('comment')
        if CommentLike.objects.filter(comment=comment, user=user).exists():
            raise forms.ValidationError(f"{user.username} has already liked this comment.")

    class Meta:
        model = CommentLike
        fields = ['comment', 'user']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'is_anon', 'reply_to', 'total_likes', 'total_dislikes', 'created_at')
    list_filter = ('is_anon', 'created_at')
    search_fields = ('body', 'user__username', 'post__title')
    readonly_fields = ('created_at', 'updated_at', 'total_likes', 'total_dislikes')
    raw_id_fields = ('user', 'post', 'reply_to')
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    form = CommentLikeForm
    list_display = ('user', 'comment', 'created_at')
    search_fields = ('user__username',)
    raw_id_fields = ('user', 'comment')


@admin.register(CommentDislike)
class CommentDislikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'created_at')
    search_fields = ('user__username',)
    raw_id_fields = ('user', 'comment')


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'emoji', 'created_at')
    list_filter = ('emoji',)
    search_fields = ('user__username',)
    raw_id_fields = ('user', 'comment')
