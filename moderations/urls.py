from django.urls import path
from . import views

app_name = 'moderations'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('reports/', views.report_queue, name='report_queue'),
    path('reports/<int:report_id>/resolve/', views.resolve_report, name='resolve_report'),
    path('posts/<int:post_id>/toggle-block/', views.toggle_block_post, name='toggle_block'),
    path('users/', views.users_list, name='users_list'),
    path('users/<int:user_id>/toggle-ban/', views.toggle_ban_user, name='toggle_ban'),
    path('blocked/', views.blocked_posts, name='blocked_posts'),
    path('stages/', views.stages_manage, name='stages_manage'),
    path('assign-mod/', views.assign_stage_moderator, name='assign_stage_moderator'),
    path('remove-mod/', views.remove_stage_moderator, name='remove_stage_moderator'),
    path('stages/<int:stage_id>/toggle/', views.toggle_stage_active, name='toggle_stage_active'),
    path('appeal/', views.appeal, name='appeal'),
]
