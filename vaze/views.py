from django.shortcuts import render
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import Length
from django.core.cache import cache
from datetime import timedelta

from posts.models import Post
from comments.models import Comment
from stages.models import Stage
from users.models import User


_SIDEBAR_CACHE_KEY = 'sidebar_ctx'
_SIDEBAR_CACHE_TTL = 120  # seconds

_HOT_GRAVITY                = 1.8
_HOT_CANDIDATE_WINDOW_HOURS = 48
_HOT_GLOBAL_LIMIT           = 300
_HOT_MIN_CANDIDATES         = 80

TOP_PERIODS = {
    'today': timedelta(hours=24),
    'week':  timedelta(days=7),
    'month': timedelta(days=30),
    'all':   None,
}
TOP_PERIOD_DEFAULT = 'today'


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _build_sidebar_context():
    cached = cache.get(_SIDEBAR_CACHE_KEY)
    if cached is not None:
        return cached

    seven_days_ago = timezone.now() - timedelta(days=7)

    trending_stages = Stage.objects.filter(is_active=True).only(
        'name', 'title', 'image', 'members_count'
    ).annotate(
        recent_post_count=Count(
            'posts',
            filter=Q(posts__created_at__gte=seven_days_ago, posts__is_published=True)
        )
    ).filter(recent_post_count__gte=2).order_by('-recent_post_count')[:5]

    stages = Stage.objects.filter(is_active=True).only(
        'name', 'title', 'image', 'members_count', 'created_at'
    ).annotate(
        post_count=Count('posts', filter=Q(posts__is_published=True))
    ).order_by('-members_count', '-created_at')[:30]

    seen_posts: set = set()
    unique_comments = []
    for c in Comment.objects.select_related('user', 'post', 'post__stage').annotate(
        body_len=Length('body')
    ).filter(
        post__is_published=True, post__is_blocked=False,
        body_len__gte=10,
    ).order_by('-created_at')[:60]:
        if c.post_id not in seen_posts:
            seen_posts.add(c.post_id)
            unique_comments.append(c)
        if len(unique_comments) >= 8:
            break

    result = {
        'trending_stages': trending_stages,
        'stages': stages,
        'comments': unique_comments,
        'total_posts': Post.objects.filter(is_published=True).count(),
        'total_users': User.objects.filter(is_active=True).count(),
        'stage_count': Stage.objects.filter(is_active=True).count(),
    }
    cache.set(_SIDEBAR_CACHE_KEY, result, timeout=_SIDEBAR_CACHE_TTL)
    return result


# ---------------------------------------------------------------------------
# Base queryset
# ---------------------------------------------------------------------------

def _base_queryset(extra_filters=None):
    base_q = Q(is_published=True, is_blocked=False)

    if extra_filters:
        base_q &= extra_filters

    return (
        Post.objects
        .filter(base_q)
        .annotate(
            like_count=Count('likes', distinct=True),
            comment_count=Count('comments', distinct=True),
            image_count=Count('images', distinct=True),
        )
        .select_related('author', 'stage')
        .prefetch_related('images')
    )


# ---------------------------------------------------------------------------
# Hot scoring
# ---------------------------------------------------------------------------

def _hot_score(post, now):
    engagement = post.like_count + post.comment_count * 2
    age_hours  = max((now - post.created_at).total_seconds() / 3600, 0)
    return engagement / ((age_hours + 2) ** _HOT_GRAVITY)


def _get_hot_posts():
    now = timezone.now()

    window_steps = [
        timedelta(hours=_HOT_CANDIDATE_WINDOW_HOURS),
        timedelta(days=7),
        timedelta(days=30),
        None,  # fallback to all time (still capped by limits)
    ]

    for window in window_steps:
        extra = Q(created_at__gte=now - window) if window else None
        candidates = list(
            _base_queryset(extra_filters=extra)
            [:_HOT_GLOBAL_LIMIT]
        )

        if len(candidates) >= _HOT_MIN_CANDIDATES or window is None:
            candidates.sort(key=lambda p: _hot_score(p, now), reverse=True)
            return candidates

    return candidates


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def index(request):
    """Homepage — delegates to Hot."""
    return hot(request)


def hot(request):
    """Hot — engagement weighted by age decay."""
    posts_list = _get_hot_posts()
    paginator  = Paginator(posts_list, 16)
    posts      = paginator.get_page(request.GET.get('page', 1))
    context    = _build_sidebar_context()
    context.update({
        'posts': posts,
        'view_type': 'hot',
    })
    return render(request, 'index.html', context)


def new(request):
    """New — pure reverse-chronological."""
    posts_list = _base_queryset().order_by('-created_at')
    paginator  = Paginator(posts_list, 16)
    posts      = paginator.get_page(request.GET.get('page', 1))
    context    = _build_sidebar_context()
    context.update({
        'posts': posts,
        'view_type': 'new',
    })
    return render(request, 'index.html', context)


def top(request):
    """Top — highest liked within a selectable time window."""
    period_key = request.GET.get('period', TOP_PERIOD_DEFAULT)
    if period_key not in TOP_PERIODS:
        period_key = TOP_PERIOD_DEFAULT

    delta = TOP_PERIODS[period_key]
    extra = Q(created_at__gte=timezone.now() - delta) if delta else None
    posts_list = _base_queryset(extra_filters=extra).order_by(
        '-like_count', '-comment_count', '-created_at'
    )
    paginator = Paginator(posts_list, 16)
    posts     = paginator.get_page(request.GET.get('page', 1))
    context   = _build_sidebar_context()
    context.update({
        'posts': posts,
        'view_type': 'top',
        'top_period': period_key,
        'top_periods': list(TOP_PERIODS),
    })
    return render(request, 'index.html', context)


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------

def rules_page(request):
    return render(request, 'rules.html')

def donate_page(request):
    return render(request, 'donate.html')

def terms_page(request):
    return render(request, 'terms.html')
