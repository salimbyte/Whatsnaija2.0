from django.core.cache import cache

from stages.models import StageModerator
from stages.mod_utils import is_platform_super_mod


def mod_context(request):
    """
    Injects mod-related context into every template:
      - user_mod_stages: list of active StageModerator records for the current user
      - is_platform_mod: True if user is staff or a super-mod

    Results are cached per-user for 5 minutes so this doesn't hit the DB on
    every single page request.  The cache is automatically invalidated when a
    mod role changes (call cache.delete(f'mod_ctx_{user.pk}') there if needed).
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'user_mod_stages': [], 'is_platform_mod': False}

    cache_key = f'mod_ctx_{request.user.pk}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    user = request.user
    mod_stages = list(
        StageModerator.objects.filter(
            user=user, is_active=True
        ).select_related('stage').order_by('stage__name')
    )
    is_platform_mod = user.is_staff or is_platform_super_mod(user)

    result = {
        'user_mod_stages': mod_stages,
        'is_platform_mod': is_platform_mod,
    }
    cache.set(cache_key, result, timeout=300)
    return result
