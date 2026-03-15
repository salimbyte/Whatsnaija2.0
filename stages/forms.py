from django import forms

from .models import Stage


class StageForm(forms.ModelForm):
    """
    Form for creating and editing stages.
    """
    class Meta:
        model = Stage
        fields = ['title', 'name', 'description', 'image']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Stage title',
                'required': True
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'stage_name (no spaces, lowercase)',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe your stage...'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def clean_name(self):
        """Validate stage name format."""
        name = self.cleaned_data.get('name')
        if ' ' in name:
            raise forms.ValidationError("Stage name cannot contain spaces. Use underscores instead.")
        if not name.islower():
            raise forms.ValidationError("Stage name must be lowercase.")
        if len(name) < 3:
            raise forms.ValidationError("Stage name must be at least 3 characters long.")
        return name
