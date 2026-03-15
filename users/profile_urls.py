from django.urls import path
from . import views

# Separate URL file for profile views (to avoid conflicts with main URLs)
app_name = 'profiles'

urlpatterns = [
    path('', views.user, name='user_profile'),
]
