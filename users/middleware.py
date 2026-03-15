from django.utils import timezone
from users.models import UserProfile


class LastSeenMiddleware:
    """
    Updates the user's last_seen timestamp on every request.
    Throttled to once per minute to avoid excessive DB writes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            # Only update once per minute (stored in session)
            last_update = request.session.get('last_seen_update', 0)
            now_ts = int(timezone.now().timestamp())

            if now_ts - last_update > 60:
                try:
                    profile, _ = UserProfile.objects.get_or_create(user=request.user)
                    # Accumulate online time — if last_seen is within 5 min,
                    # add the elapsed seconds to total_time_online
                    if profile.last_seen:
                        gap = now_ts - int(profile.last_seen.timestamp())
                        if gap <= 300:  # 5 minutes = still "online"
                            profile.total_time_online += gap
                    profile.last_seen = timezone.now()
                    profile.save(update_fields=['last_seen', 'total_time_online'])
                    request.session['last_seen_update'] = now_ts
                except Exception:
                    pass

        return response
