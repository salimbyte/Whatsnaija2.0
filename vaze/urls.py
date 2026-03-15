from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from .views import index, hot, new, top, rules_page, donate_page, terms_page

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # CKEditor
    path('ckeditor/', include('ckeditor_uploader.urls')),

    # Main feed pages
    path('',     index, name='home'),
    path('hot/', hot,   name='hot'),
    path('new/', new,   name='new'),
    path('top/', top,   name='top'),

    # Static pages
    path('rules/',  rules_page,  name='rules'),
    path('donate/', donate_page, name='donate'),
    path('terms/',  terms_page,  name='terms'),

    # App URLs
    path('posts/',    include('posts.urls')),
    path('s/',        include('stages.urls')),
    path('users/',    include('users.urls')),
    path('mod/',      include('moderations.urls')),
    path('accounts/', include('allauth.urls')),

    # User profile catch-all — must stay last
    path('<str:username>/', include('users.profile_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)