from django.contrib import admin
from django import forms
from .models import Post, PostImage, Like, DisLike
from admin_searchable_dropdown.filters import AutocompleteFilter




class LikeModelForm(forms.ModelForm):
   
    def clean(self):
        user = self.cleaned_data.get('user')
        post = self.cleaned_data.get('post')

        existing_like  = Like.objects.filter(post=post, user=user).exists()
        if existing_like:
            raise forms.ValidationError(f"This user '{user.username}' have already liked this post. can't like twice!")
     

        existing_dislike  = DisLike.objects.filter(post=post, user=user).first()
        if existing_dislike != None:
            existing_dislike.delete()

    class Meta:
        model = Like
        fields = ['post', 'user']

class DisLikeModelForm(forms.ModelForm):

    def clean(self):
        user = self.cleaned_data.get('user')
        post = self.cleaned_data.get('post')
        if DisLike.objects.filter(post=post, user=user).exists():
            raise forms.ValidationError(f"'{user.username}' has already disliked this post.")
        existing_like = Like.objects.filter(post=post, user=user).first()
        if existing_like:
            existing_like.delete()

    class Meta:
        model = DisLike
        fields = ['post', 'user']

class LikeFilter(AutocompleteFilter):
    title = 'post' # display title
    field_name = 'post' # name of the foreign key field

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_filter = [LikeFilter]
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__username', 'post__title')
    raw_id_fields = ('user', 'post')
    form = LikeModelForm

@admin.register(DisLike)
class DisLikeAdmin(admin.ModelAdmin):
    form = DisLikeModelForm
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__username', 'post__title')
    raw_id_fields = ('user', 'post')


        

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Admin interface for Post model."""
    list_filter = ("created_at", "is_blocked", "is_published", "author")
    search_fields = ("title", "body", "author__username")
    list_display = ['title', 'author', 'stage', 'is_published', 'is_blocked', 'total_likes', 'total_dislikes', 'created_at']
    readonly_fields = ('slug', 'created_at', 'updated_at', 'total_likes', 'total_dislikes')
    list_editable = ['is_published', 'is_blocked']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(PostImage)
class PostImageAdmin(admin.ModelAdmin):
    """Admin interface for PostImage model."""
    list_display = ('post', 'image', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('post__title',)
    readonly_fields = ('uploaded_at',)