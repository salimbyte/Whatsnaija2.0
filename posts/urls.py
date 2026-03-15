from django.urls import path
from . import views

app_name = 'posts'

urlpatterns = [
    path('create/', views.create, name='create'),
    path('search/', views.search, name='search'),
    path('saved/', views.saved_posts, name='saved'),
    path('report/', views.report_content, name='report'),
    path('comments/<int:comment_id>/replies/', views.load_replies, name='load_replies'),
    path('<str:slug>/', views.post, name='detail'),
    path('<int:post_id>/edit/', views.edit_post, name='edit'),
    path('<int:post_id>/delete/', views.delete_post, name='delete'),
    path('<int:post_id>/<str:slug>/makecomment/', views.comment, name='make_comment'),
    path('<int:post_id>/<str:slug>/like/', views.like, name='like'),
    path('<int:post_id>/<str:slug>/dislike/', views.dislike, name='dislike'),
    path('<int:post_id>/comments/<int:comment_id>/like/', views.comment_like, name='comment_like'),
    path('<int:post_id>/comments/<int:comment_id>/dislike/', views.comment_dislike, name='comment_dislike'),
    path('<int:post_id>/comments/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('<int:post_id>/comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('<int:post_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
]