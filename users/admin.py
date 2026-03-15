from django.contrib import admin

from .models import User, UserProfile, Follow, Message, Notification, MessageReaction, ReservedUsername


class ProfileInline(admin.StackedInline):
    """Inline admin for user profile."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    fields = ('avatar', 'bio', 'location', 'birth_date', 'profile_views')
    readonly_fields = ('profile_views',)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin interface for User model."""
    change_user_password_template = None

    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_verified", "email_verified", "ban_until")
    list_filter = ("is_staff", "is_superuser", "is_active", "is_verified", "email_verified", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    readonly_fields = ('password', 'last_login', 'date_joined')
    inlines = [ProfileInline]

    filter_horizontal = (
        "groups",
        "user_permissions",
    )
    
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "gender")}),
        ("Academic", {"fields": ("course", "stage")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "is_verified", "email_verified", "ban_until")}),
        ("Groups", {"fields": ("groups", "user_permissions")}),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'location', 'profile_views', 'online_status', 'created_at')
    search_fields = ('user__username', 'user__email', 'location')
    readonly_fields = ('profile_views', 'online_status', 'is_online', 'created_at', 'updated_at')
    list_filter = ('created_at',)


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'following', 'created_at')
    search_fields = ('follower__username', 'following__username')
    raw_id_fields = ('follower', 'following')
    ordering = ['-created_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('sender__username', 'recipient__username', 'body')
    readonly_fields = ('created_at',)
    raw_id_fields = ('sender', 'recipient')
    ordering = ['-created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'sender', 'notification_type', 'text', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'sender__username', 'text')
    readonly_fields = ('created_at',)
    raw_id_fields = ('recipient', 'sender')
    list_editable = ('is_read',)
    ordering = ['-created_at']


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ('reactor', 'message', 'created_at')
    search_fields = ('reactor__username',)
    raw_id_fields = ('reactor', 'message')
    ordering = ['-created_at']


@admin.register(ReservedUsername)
class ReservedUsernameAdmin(admin.ModelAdmin):
    list_display = ('name', 'reason', 'created_at')
    search_fields = ('name', 'reason')
    readonly_fields = ('created_at',)
    ordering = ['name_lower']
