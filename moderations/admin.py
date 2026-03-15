from django.contrib import admin
from .models import Report, ModAction


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'content_type', 'report_type', 'status', 'created_at')
    list_filter = ('status', 'report_type', 'content_type')
    search_fields = ('reporter__username', 'description')
    raw_id_fields = ('reporter', 'reviewed_by', 'post', 'comment')


@admin.register(ModAction)
class ModActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'moderator', 'action', 'stage', 'target_user', 'created_at')
    list_filter = ('action',)
    search_fields = ('moderator__username', 'target_user__username', 'reason')
    raw_id_fields = ('moderator', 'target_user', 'target_post', 'target_comment', 'stage')
