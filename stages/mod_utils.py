"""
Stage moderation permission helpers.

Hierarchy (highest → lowest):
  1. Django staff (is_staff)          — full platform access
  2. Stage mod (StageModerator record) — assigned stage only
"""


def can_moderate_stage(user, stage):
    """Return True if *user* may moderate *stage*."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    from stages.models import StageModerator
    return StageModerator.objects.filter(
        user=user,
        is_active=True,
        stage=stage,
    ).exists()


def can_assign_mods(user, stage):
    """Return True if *user* may add/remove moderators for *stage*."""
    if not user.is_authenticated:
        return False
    return user.is_staff


def mod_required(view_func):
    """Decorator: user must be able to moderate the stage passed as stage_name kwarg."""
    from functools import wraps
    from django.shortcuts import redirect, get_object_or_404
    from django.contrib import messages
    from stages.models import Stage

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/users/login/?next={request.path}')
        stage_name = kwargs.get('stage_name')
        stage = get_object_or_404(Stage, name=stage_name)
        if not stage.is_active and not request.user.is_staff:
            messages.error(request, "This stage is currently disabled by staff.")
            return redirect('/')
        if not can_moderate_stage(request.user, stage):
            messages.error(request, "You don't have permission to moderate this stage.")
            return redirect('stages:stage_page', stage_name=stage.name)
        return view_func(request, *args, **kwargs)
    return wrapper
