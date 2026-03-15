from django import forms
from django.forms import modelformset_factory

from .models import Post, PostImage


class PostForm(forms.ModelForm):
    """
    Form for creating and editing posts.
    """
    class Meta:
        model = Post
        fields = ['title', 'body', 'stage', 'url']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Post title',
                'required': True
            }),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Post content...'
            }),
            'stage': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com (optional)'
            }),
        }
    
    def clean_title(self):
        """Validate title length and content."""
        title = self.cleaned_data.get('title')
        if len(title) < 3:
            raise forms.ValidationError("Title must be at least 3 characters long.")
        return title


class PostImageForm(forms.ModelForm):
    """
    Form for uploading post images.
    """
    image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        })
    )
    
    class Meta:
        model = PostImage
        fields = ['image']


# FormSet for multiple image uploads
PostImageFormSet = modelformset_factory(
    PostImage,
    form=PostImageForm,
    extra=6,
    max_num=6,
    can_delete=True
)
