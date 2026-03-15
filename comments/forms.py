from django import forms

from .models import Comment

IMAGE_ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


class CommentForm(forms.ModelForm):
    """
    Form for creating comments on posts.
    """
    class Meta:
        model = Comment
        fields = ['body', 'is_anon', 'image']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Write a comment...',
                'required': True
            }),
            'is_anon': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'image': forms.ClearableFileInput(attrs={
                'accept': 'image/jpeg,image/png,image/gif,image/webp',
            }),
        }
        labels = {
            'body': 'Comment',
            'is_anon': 'Post anonymously',
            'image': 'Attach image / GIF',
        }

    def clean_body(self):
        """Validate comment body."""
        body = self.cleaned_data.get('body')
        if len(body) < 1:
            raise forms.ValidationError("Comment cannot be empty.")
        return body

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if img:
            if img.size > IMAGE_MAX_BYTES:
                raise forms.ValidationError("Image must be under 5 MB.")
            if img.content_type not in IMAGE_ALLOWED_TYPES:
                raise forms.ValidationError("Only JPEG, PNG, GIF, and WebP images are allowed.")
        return img
