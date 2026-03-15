from django.urls import path
from .views import (
    stage_page, create_stage, edit_stage,
    mod_dashboard, mod_queue, mod_resolve_report, mod_remove_post,
    mod_ban_user, mod_unban_user, mod_members,
    mod_add_moderator, mod_remove_moderator, mod_log,
    join_stage, my_mod_overview, stages_list,
)

app_name = 'stages'

urlpatterns = [
    path('', stages_list, name='stages'),
    path('create/', create_stage, name='create'),
    path('mod/', my_mod_overview, name='my_mod_overview'),
    path('<str:stage_name>/edit/', edit_stage, name='edit'),

    # ── Stage moderation ──────────────────────────────────────
    path('<str:stage_name>/mod/', mod_dashboard, name='mod_dashboard'),
    path('<str:stage_name>/mod/queue/', mod_queue, name='mod_queue'),
    path('<str:stage_name>/mod/queue/<int:report_id>/resolve/', mod_resolve_report, name='mod_resolve_report'),
    path('<str:stage_name>/mod/posts/<int:post_id>/remove/', mod_remove_post, name='mod_remove_post'),
    path('<str:stage_name>/mod/ban/', mod_ban_user, name='mod_ban'),
    path('<str:stage_name>/mod/unban/<int:ban_id>/', mod_unban_user, name='mod_unban'),
    path('<str:stage_name>/mod/members/', mod_members, name='mod_members'),
    path('<str:stage_name>/mod/members/add/', mod_add_moderator, name='mod_add_moderator'),
    path('<str:stage_name>/mod/members/<int:mod_id>/remove/', mod_remove_moderator, name='mod_remove_moderator'),
    path('<str:stage_name>/mod/log/', mod_log, name='mod_log'),

    path('<str:stage_name>/join/', join_stage, name='join_stage'),

    # ── Stage page (keep last — catch-all) ──────────────────
    path('<str:stage_name>/', stage_page, name='stage_page'),
]

