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
    path('appeal/', views.appeal, name='appeal'),
    # Super-mod management (staff only)
    path('super-mods/', views.manage_super_mods, name='super_mods'),
    path('super-mods/<int:mod_id>/remove/', views.remove_super_mod, name='remove_super_mod'),
]
