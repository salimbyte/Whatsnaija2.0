from django.urls import path
from . import views
app_name = 'users'

urlpatterns = [
    path("login/", views.login_user, name="login"),
    path("register/", views.register, name="register"),
    path("username-check/", views.username_check, name="username_check"),
    path("logout/", views.logout_user, name="logout"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("password/change/", views.change_password, name="change_password"),
    path("inbox/", views.inbox, name="inbox"),
    path("inbox/poll/", views.inbox_poll, name="inbox_poll"),
    path("messages/<str:username>/", views.conversation, name="conversation"),
    path("messages/<str:username>/poll/", views.messages_poll, name="messages_poll"),
    path("messages/<str:username>/typing/", views.typing_signal, name="typing_signal"),
    path("messages/<int:message_id>/react/", views.react_message, name="react_message"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/mark-read/", views.mark_all_read, name="mark_all_read"),
    path("notifications/count/", views.notifications_count, name="notifications_count"),
    path("follow/<str:username>/", views.toggle_follow, name="toggle_follow"),
]
