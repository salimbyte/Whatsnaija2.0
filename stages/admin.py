from django.contrib import admin
from .models import Stage, StageModerator, StageBan


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'admin', 'members_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'title', 'description', 'admin__username')
    readonly_fields = ('created_at', 'updated_at', 'members_count')
    raw_id_fields = ('admin',)
    list_editable = ('is_active',)
    ordering = ['-created_at']


@admin.register(StageModerator)
class StageModeratorAdmin(admin.ModelAdmin):
    list_display = ('user', 'stage', 'is_super_mod', 'is_active', 'added_by', 'created_at')
    list_filter = ('is_super_mod', 'is_active')
    search_fields = ('user__username', 'stage__name')
    raw_id_fields = ('user', 'stage', 'added_by')
    list_editable = ('is_active',)
    ordering = ['-created_at']


@admin.register(StageBan)
class StageBanAdmin(admin.ModelAdmin):
    list_display = ('user', 'stage', 'banned_by', 'reason', 'expires_at', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__username', 'stage__name', 'reason')
    raw_id_fields = ('user', 'stage', 'banned_by')
    list_editable = ('is_active',)
    ordering = ['-created_at']
