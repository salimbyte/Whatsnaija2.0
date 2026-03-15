"""
Shared utility functions used across multiple apps.
Centralised here to avoid copy-pasting the same helpers into every app.
"""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from users.models import Notification


# Phrases so generic they add no information to a moderation reason.
_TAUTOLOGICAL_REASONS = {
    'moderator removal', 'removed', 'banned', 'rule violation',
    'violation', 'mod action', 'moderation', 'removal',
}

_SHORT_OK_REASONS = {
    'spam', 'nsfw', 'scam',
}


def clean_reason(reason):
    """Return reason only if it is meaningfully descriptive, else empty string."""
    if not reason:
        return ''
    cleaned = reason.lower().strip('.')
    if cleaned in _TAUTOLOGICAL_REASONS:
        return ''
    if len(cleaned) < 5 and cleaned not in _SHORT_OK_REASONS:
        return ''
    return reason


def send_notification(recipient, sender, notification_type, text, link):
    """
    Create a Notification.  Centralised so callers do not repeat the same
    five keyword-argument block everywhere.

    recipient       — User instance to notify
    sender          — User instance (or None for system messages)
    notification_type — string matching Notification.NOTIFICATION_TYPES choices
    text            — human-readable notification text
    link            — relative URL to navigate to when tapped
    """
    if recipient is None:
        return None
    notif = Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        text=text,
        link=link,
    )
    # Invalidate the cached notification count so the recipient sees the new notification
    # within at most one poll cycle rather than waiting for TTL expiry.
    cache.delete(f'notif_count_{recipient.pk}')
    return notif


BAN_DURATION_MAP = {
    '24h': timedelta(hours=24),
    '3d': timedelta(days=3),
    '7d': timedelta(days=7),
    'permanent': None,
}


def ban_until_from_key(key: str):
    key = (key or '').strip().lower()
    if key not in BAN_DURATION_MAP:
        return None
    delta = BAN_DURATION_MAP[key]
    return None if delta is None else timezone.now() + delta
