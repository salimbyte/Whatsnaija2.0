from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from PIL import Image

from .models import UserProfile, is_reserved_username, USERNAME_MAX_LENGTH

User = get_user_model()


class UserRegistrationForm(UserCreationForm):
    """
    Form for user registration.
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email'
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
        }

    def clean_email(self):
        """Ensure email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if username and len(username) < 3:
            raise forms.ValidationError("Username must be at least 3 characters.")
        if username and len(username) > USERNAME_MAX_LENGTH:
            raise forms.ValidationError(f"Username must be {USERNAME_MAX_LENGTH} characters or fewer.")
        if username and is_reserved_username(username):
            raise forms.ValidationError("This username is reserved.")
        return username


class UserLoginForm(AuthenticationForm):
    """
    Form for user login.
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )


class UserProfileForm(forms.ModelForm):
    """
    Form for updating user profile.
    """
    class Meta:
        model = UserProfile
        fields = ['avatar', 'banner', 'bio', 'location', 'birth_date']
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Tell us about yourself...',
                'maxlength': 500,
            }),
            'location': forms.TextInput(attrs={
                'placeholder': 'e.g. Baghdad, Iraq',
            }),
            'birth_date': forms.DateInput(attrs={
                'type': 'date',
            }),
            'avatar': forms.FileInput(attrs={
                'accept': 'image/*',
            }),
            'banner': forms.FileInput(attrs={
                'accept': 'image/*',
            }),
        }
        labels = {
            'avatar': 'Profile photo',
            'banner': 'Banner image',
            'bio': 'Bio',
            'location': 'Location',
            'birth_date': 'Date of birth',
        }


class UserUpdateForm(forms.ModelForm):
    """
    Form for updating user basic information.
    """
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'gender', 'course', 'stage']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'gender': forms.Select(),
            'course': forms.TextInput(attrs={'placeholder': 'e.g. Computer Science'}),
            'stage': forms.TextInput(attrs={'placeholder': 'e.g. 3rd Year'}),
        }
        labels = {
            'first_name': 'First name',
            'last_name': 'Last name',
            'email': 'Email',
            'gender': 'Gender',
            'course': 'Course / Major',
            'stage': 'Stage / Year',
        }


class PhotoForm(forms.ModelForm):
    """
    Form for cropping user profile photos.
    """
    x = forms.FloatField(widget=forms.HiddenInput())
    y = forms.FloatField(widget=forms.HiddenInput())
    width = forms.FloatField(widget=forms.HiddenInput())
    height = forms.FloatField(widget=forms.HiddenInput())

    class Meta:
        model = UserProfile
        fields = ('avatar', 'x', 'y', 'width', 'height')

    def save(self, commit=True):
        """Save and crop the photo."""
        photo = super(PhotoForm, self).save(commit=False)

        x = self.cleaned_data.get('x')
        y = self.cleaned_data.get('y')
        w = self.cleaned_data.get('width')
        h = self.cleaned_data.get('height')

        if photo.avatar and x is not None and y is not None:
            image = Image.open(photo.avatar)
            cropped_image = image.crop((x, y, w+x, h+y))
            resized_image = cropped_image.resize((200, 200), Image.LANCZOS)
            resized_image.save(photo.avatar.path)

        if commit:
            photo.save()
        
        return photo
