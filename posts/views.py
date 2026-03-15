import re
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.db.models import Q, Count, F
from django.db.models.functions import Length
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Post, PostImage, Like, DisLike, Bookmark
from .forms import PostForm, PostImageFormSet
from .og_scraper import fetch_og_image_async
from comments.models import Comment, CommentLike, CommentDislike
from comments.forms import CommentForm
from django.core.paginator import Paginator

from stages.models import Stage, StageBan
from stages.mod_utils import can_moderate_stage
from moderations.models import Report
from users.models import Notification
from vaze.utils import send_notification, clean_reason

User = get_user_model()


def _active_stage_ban(user, stage):
    if not user or not stage:
        return None
    now = timezone.now()
    StageBan.objects.filter(is_active=True, expires_at__lt=now).update(is_active=False)
    return StageBan.objects.filter(
        user=user, stage=stage, is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).first()


@login_required(login_url='/users/login/')
def create(request):
    """
    Create a new post with optional images.
    """
    if request.user.is_staff:
        stages = Stage.objects.all()
    else:
        stages = Stage.objects.filter(is_active=True)
    postform = PostForm()
    formset = PostImageFormSet(queryset=PostImage.objects.none())

    if request.method == 'POST':
        postform = PostForm(request.POST)
        formset = PostImageFormSet(request.POST, request.FILES)
        
        if postform.is_valid() and formset.is_valid():
            # Save post
            post = postform.save(commit=False)
            post.author = request.user

            # Check stage ban before saving
            if post.stage:
                ban = _active_stage_ban(request.user, post.stage)
                if ban:
                    reason = clean_reason(ban.reason)
                    until = (
                        f" Ban ends {timezone.localtime(ban.expires_at).strftime('%b %d, %Y %H:%M')}."
                        if ban.expires_at else ""
                    )
                    reason_txt = f" Reason: {reason}." if reason else ""
                    messages.error(
                        request,
                        f"You are banned from posting in s/{post.stage.name}.{until}{reason_txt}"
                    )
                    return render(request, "posts/create.html", {
                        "stages": stages, 'form': postform, 'formset': formset
                    })
                if not post.stage.is_active and not request.user.is_staff:
                    messages.error(request, f"s/{post.stage.name} is currently disabled by staff.")
                    return render(request, "posts/create.html", {
                        "stages": stages, 'form': postform, 'formset': formset
                    })

            post.save()
            postform.save_m2m()

            # Fire background OG image scrape for link posts
            if post.url:
                fetch_og_image_async(post.pk, post.url)

            # Save images
            for form in formset:
                if form.cleaned_data.get('image'):
                    image = form.cleaned_data['image']
                    PostImage.objects.create(post=post, image=image)
            
            messages.success(request, "Post created successfully!")
            return redirect('posts:detail', slug=post.slug)
        else:
            messages.error(request, "Please correct the errors below.")
 
    return render(request, "posts/create.html", {
        "stages": stages,
        'form': postform,
        'formset': formset
    })


def post(request, slug):
    """
    Display a single post with comments and related content.
    Falls back to title lookup for old-style links, then redirects to slug URL.
    """
    post = Post.objects.filter(slug=slug).first()
    if post is None:
        # Legacy URLs used raw titles — find by title and redirect
        post = Post.objects.filter(title=slug).first()
        if post is None:
            raise Http404("No Post matches the given query.")
        return redirect('posts:detail', slug=post.slug, permanent=True)
    # Blocked posts are only visible to mods/staff
    if post.is_blocked:
        is_mod = (
            request.user.is_authenticated
            and post.stage
            and can_moderate_stage(request.user, post.stage)
        ) or (request.user.is_authenticated and request.user.is_staff)
        if not is_mod:
            messages.error(request, 'This post has been removed by a moderator.')
            return redirect(f'/s/{post.stage.name}/' if post.stage else '/')
    if post.stage and not post.stage.is_active and not request.user.is_staff:
        messages.error(request, 'This stage is currently disabled by staff.')
        return redirect('/')
    suggests = Post.objects.filter(
        is_published=True, is_blocked=False
    ).exclude(pk=post.pk).select_related('author', 'stage').prefetch_related('images').order_by('-created_at').distinct()[:15]

    # Related posts from same stage — deduplicated by pk ordering
    similar_posts = Post.objects.filter(
        stage=post.stage, is_blocked=False
    ).exclude(pk=post.pk).select_related('author', 'stage').prefetch_related('images').order_by('-created_at').distinct()[:5]

    # Increment view count (once per session per post)
    viewed_key = f'viewed_post_{post.pk}'
    if not request.session.get(viewed_key):
        Post.objects.filter(pk=post.pk).update(view_count=F('view_count') + 1)
        request.session[viewed_key] = True

    # Reading time estimate at 200 words per minute
    body_text = re.sub(r'<[^>]+>', '', post.body or '')
    word_count = len(body_text.split())
    read_time = max(1, round(word_count / 200))

    # Track user likes on comments
    user_likes = []
    user_dislikes = []
    is_liked = False
    is_disliked = False

    if request.user.is_authenticated:
        # Fetch comment IDs once to avoid evaluating the subquery twice
        comment_ids = list(post.comments.values_list('id', flat=True))
        user_likes = list(CommentLike.objects.filter(
            user=request.user,
            comment_id__in=comment_ids
        ).values_list('comment_id', flat=True))
        user_dislikes = list(CommentDislike.objects.filter(
            user=request.user,
            comment_id__in=comment_ids
        ).values_list('comment_id', flat=True))

        is_liked = Like.objects.filter(user=request.user, post=post).exists()
        is_disliked = DisLike.objects.filter(user=request.user, post=post).exists()

    is_bookmarked = (
        request.user.is_authenticated
        and Bookmark.objects.filter(user=request.user, post=post).exists()
    )

    # Evaluate top_comments once and reuse for the count — avoids a second COUNT query
    top_comments = list(
        post.comments
        .filter(reply_to__isnull=True)
        .select_related('user', 'user__profile')
        .annotate(like_count=Count('commentlikes'))
        .order_by('-like_count', '-created_at')
    )

    context = {
        "user_likes": user_likes,
        "user_dislikes": user_dislikes,
        "is_liked": is_liked,
        "is_disliked": is_disliked,
        "is_bookmarked": is_bookmarked,
        "post": post,
        "suggests": suggests,
        'similar_posts': similar_posts,
        'read_time': read_time,
        'top_comments': top_comments,
        'top_comment_count': len(top_comments),
        'comment_highlight': int(request.GET.get('comment_highlight', 0)),
    }
    
    return render(request, "posts/post.html", context)


def comment(request, post_id, slug):
    """
    Handle comment submission on a post (including nested replies).
    """
    post = get_object_or_404(Post, id=post_id)
    
    if request.method == "POST":
        comment_form = CommentForm(request.POST, request.FILES)
        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            
            # Set user (None if anonymous)
            if new_comment.is_anon or not request.user.is_authenticated:
                new_comment.user = None
                new_comment.is_anon = True
            else:
                new_comment.user = request.user

            # Check stage ban for authenticated non-anon comments
            if new_comment.user and post.stage:
                ban = _active_stage_ban(new_comment.user, post.stage)
                if ban:
                    reason = clean_reason(ban.reason)
                    until = (
                        f" Ban ends {timezone.localtime(ban.expires_at).strftime('%b %d, %Y %H:%M')}."
                        if ban.expires_at else ""
                    )
                    reason_txt = f" Reason: {reason}." if reason else ""
                    messages.error(
                        request,
                        f"You are banned from commenting in s/{post.stage.name}.{until}{reason_txt}"
                    )
                    return redirect('posts:detail', slug=post.slug)
        
            new_comment.post = post

            # Save Tenor GIF URL if one was picked (and no file was uploaded)
            gif_url = request.POST.get('gif_url', '').strip()
            if gif_url and not new_comment.image:
                # Basic safety: only allow tenor CDN URLs (v1: media1/media.tenor.com, v2: c.tenor.com)
                if (gif_url.startswith('https://media.tenor.com/') or
                        gif_url.startswith('https://media1.tenor.com/') or
                        gif_url.startswith('https://c.tenor.com/')):
                    new_comment.gif_url = gif_url

            # Attach directly to the intended parent (true deep nesting)
            reply_to_id = request.POST.get('reply_to')
            if reply_to_id:
                try:
                    parent_comment = Comment.objects.get(id=reply_to_id, post=post)
                    new_comment.reply_to = parent_comment
                except Comment.DoesNotExist:
                    pass
            
            new_comment.save()

            # ── Notifications (skip anon comments) ──────────────
            if not new_comment.is_anon and new_comment.user:
                commenter = new_comment.user
                comment_link = (
                    f'/posts/{post.slug}/'
                    f'?comment_highlight={new_comment.id}'
                    f'#comment-{new_comment.id}'
                )
                if (
                    new_comment.reply_to
                    and new_comment.reply_to.user
                    and new_comment.reply_to.user != commenter
                ):
                    # Notify parent comment author of reply
                    send_notification(
                        recipient=new_comment.reply_to.user,
                        sender=commenter,
                        notification_type='reply',
                        text=f'{commenter.username} replied to your comment',
                        link=comment_link,
                    )
                elif post.author != commenter:
                    # Notify post author of new top-level comment
                    send_notification(
                        recipient=post.author,
                        sender=commenter,
                        notification_type='comment',
                        text=f'{commenter.username} commented on "{post.title[:60]}"',
                        link=comment_link,
                    )
                # @mention notifications — bulk-fetch mentioned users in one query
                User = get_user_model()
                raw_mentions = set(re.findall(r'@(\w+)', new_comment.body))
                raw_mentions.discard(commenter.username.lower())
                if raw_mentions:
                    mentioned_users = {
                        u.username.lower(): u
                        for u in User.objects.filter(username__in=raw_mentions)
                    }
                    for mentioned_user in mentioned_users.values():
                        if mentioned_user != post.author or new_comment.reply_to:  # avoid double-notify post author
                            send_notification(
                                recipient=mentioned_user,
                                sender=commenter,
                                notification_type='mention',
                                text=f'{commenter.username} mentioned you in a comment',
                                link=comment_link,
                            )

            messages.success(request, "Comment posted successfully!")
            return redirect(f'/posts/{post.slug}/?comment_highlight={new_comment.id}#comment-{new_comment.id}')
        else:
            messages.error(request, "Failed to post comment.")
    
    return redirect('posts:detail', slug=post.slug)


def load_replies(request, comment_id):
    """
    AJAX: return paginated replies for a comment as an HTML fragment.
    Page 1 is rendered server-side; this serves page 2 onward.
    """
    INITIAL  = 3   # must match REPLIES_INITIAL in comment.html
    PER_LOAD = 5

    parent = get_object_or_404(Comment, id=comment_id)

    try:
        page  = max(2, int(request.GET.get('page', 2)))
        depth = max(0, int(request.GET.get('depth', 1)))
    except (TypeError, ValueError):
        page, depth = 2, 1

    offset  = INITIAL + (page - 2) * PER_LOAD
    replies = parent.replies.select_related(
        'user', 'user__profile'
    ).order_by('created_at')[offset: offset + PER_LOAD]

    total     = parent.replies.count()
    has_more  = total > offset + PER_LOAD
    remaining = max(0, total - (offset + PER_LOAD))

    user_likes = []
    user_dislikes = []
    if request.user.is_authenticated:
        user_likes = list(CommentLike.objects.filter(
            user=request.user,
            comment__in=parent.replies.all()
        ).values_list('comment_id', flat=True))
        user_dislikes = list(CommentDislike.objects.filter(
            user=request.user,
            comment__in=parent.replies.all()
        ).values_list('comment_id', flat=True))

    html = render_to_string(
        'posts/includes/reply_list.html',
        {
            'replies'   : replies,
            'user_likes': user_likes,
            'user_dislikes': user_dislikes,
            'post'      : parent.post,
            'depth'     : depth,
        },
        request=request,
    )

    return JsonResponse({
        'html'     : html,
        'has_more' : has_more,
        'remaining': remaining,
        'next_page': page + 1,
    })


def _toggle_post_reaction(request, post_id, reaction_model, opposite_model, liked_action, unliked_action):
    """
    Shared toggle logic for post likes and dislikes.
    Returns a JsonResponse with the updated counts.
    Uses delete() return value to avoid a separate exists() check (saves 1–2 queries).
    """
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method.'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required. Please log in.'}, status=401)

    post = get_object_or_404(Post, id=post_id)
    user = request.user

    # delete() returns (count, detail_dict) — if count > 0 the reaction existed
    deleted_count, _ = reaction_model.objects.filter(user=user, post=post).delete()
    if deleted_count:
        action = unliked_action
    else:
        reaction_model.objects.create(user=user, post=post)
        action = liked_action
        if reaction_model is Like and post.author != user:
            # Upsert a single like notification per user/post pair to avoid spam
            Notification.objects.get_or_create(
                recipient=post.author,
                sender=user,
                notification_type='like',
                link=f'/posts/{post.slug}/',
                defaults={
                    'text': f'{user.username} liked your post "{post.title[:60]}"',
                    'is_read': False,
                },
            )

    # Remove the opposite reaction unconditionally — safe to call even when absent
    opposite_deleted, _ = opposite_model.objects.filter(user=user, post=post).delete()
    second_action = ('unliked' if opposite_model is Like else 'undisliked') if opposite_deleted else 'nothing'

    # Fetch both counts in a single annotated query
    counts = Post.objects.filter(pk=post.pk).annotate(
        like_c=Count('likes', distinct=True),
        dislike_c=Count('dislikes', distinct=True),
    ).values('like_c', 'dislike_c').first()

    return JsonResponse({
        'action': action,
        'second_action': second_action,
        'new_likes_count': counts['like_c'],
        'new_dislikes_count': counts['dislike_c'],
    })


def like(request, post_id, slug):
    """Toggle like on a post via AJAX."""
    return _toggle_post_reaction(request, post_id, Like, DisLike, 'liked', 'unliked')


def dislike(request, post_id, slug):
    """Toggle dislike on a post via AJAX."""
    return _toggle_post_reaction(request, post_id, DisLike, Like, 'disliked', 'undisliked')


def _toggle_comment_reaction(request, post_id, comment_id, reaction_model, opposite_model, liked_action, unliked_action):
    """
    Shared toggle logic for comment likes and dislikes.
    Returns a JsonResponse with the updated counts.
    """
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method.'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required. Please log in.'}, status=401)

    get_object_or_404(Post, id=post_id)
    comment = get_object_or_404(Comment, id=comment_id)
    user = request.user

    already_reacted, _ = reaction_model.objects.filter(user=user, comment=comment).delete()
    if already_reacted:
        action = unliked_action
    else:
        reaction_model.objects.create(user=user, comment=comment)
        # Remove the opposite reaction when adding one
        opposite_model.objects.filter(user=user, comment=comment).delete()
        action = liked_action

    # Single annotated query for both counts
    counts = Comment.objects.filter(pk=comment.pk).annotate(
        like_c=Count('commentlikes', distinct=True),
        dislike_c=Count('commentdislikes', distinct=True),
    ).values('like_c', 'dislike_c').first()

    return JsonResponse({
        'action': action,
        'new_likes_count': counts['like_c'],
        'new_dislikes_count': counts['dislike_c'],
    })


def comment_like(request, post_id, comment_id):
    """Toggle like on a comment via AJAX."""
    return _toggle_comment_reaction(request, post_id, comment_id, CommentLike, CommentDislike, 'liked', 'unliked')


def comment_dislike(request, post_id, comment_id):
    """Toggle dislike on a comment via AJAX."""
    return _toggle_comment_reaction(request, post_id, comment_id, CommentDislike, CommentLike, 'disliked', 'undisliked')


@login_required(login_url='/users/login/')
def edit_post(request, post_id):
    """
    Edit an existing post.
    """
    post = get_object_or_404(Post, id=post_id)
    
    # Check permissions
    if request.user != post.author and not request.user.is_staff:
        messages.error(request, "You don't have permission to edit this post.")
        return redirect('posts:detail', slug=post.slug)
    
    stages = Stage.objects.all()
    
    if request.method == 'POST':
        postform = PostForm(request.POST, instance=post)
        
        if postform.is_valid():
            postform.save()
            messages.success(request, "Post updated successfully!")
            return redirect('posts:detail', slug=post.slug)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        postform = PostForm(instance=post)
    
    return render(request, "posts/edit.html", {
        "stages": stages,
        'form': postform,
        'post': post
    })


@login_required(login_url='/users/login/')
def delete_post(request, post_id):
    """
    Delete a post.
    """
    post = get_object_or_404(Post, id=post_id)
    
    # Check permissions
    if request.user != post.author and not request.user.is_staff:
        messages.error(request, "You don't have permission to delete this post.")
        return redirect('posts:detail', slug=post.slug)
    
    if request.method == 'POST':
        post_title = post.title
        post.delete()
        messages.success(request, f"Post '{post_title}' has been deleted.")
        return redirect('/')
    
    return render(request, "posts/delete_confirm.html", {'post': post})


@login_required(login_url='/users/login/')
@require_POST
def edit_comment(request, post_id, comment_id):
    """Edit a comment via AJAX."""
    comment = get_object_or_404(Comment, id=comment_id, post_id=post_id)

    if request.user != comment.user and not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'error': 'Comment cannot be empty.'}, status=400)

    comment.body = body
    comment.save()

    return JsonResponse({'success': True, 'body': comment.body})


@login_required(login_url='/users/login/')
@require_POST
def delete_comment(request, post_id, comment_id):
    """Delete a comment via AJAX."""
    comment = get_object_or_404(Comment, id=comment_id, post_id=post_id)

    if request.user != comment.user and not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    comment.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/users/login/')
@require_POST
def report_content(request):
    """Submit a report for a post or comment."""
    content_type = request.POST.get('content_type')
    report_type = request.POST.get('report_type', 'other').strip().lower().replace(' ', '_')
    # Normalize to valid choices
    valid_types = {'spam', 'harassment', 'hate_speech', 'misinformation', 'nsfw', 'other'}
    if report_type not in valid_types:
        report_type = 'other'
    description = request.POST.get('description', '').strip()[:500]

    # Rate limit: 10 reports per hour per user
    one_hour_ago = timezone.now() - timedelta(hours=1)
    if Report.objects.filter(
        reporter=request.user,
        created_at__gte=one_hour_ago,
        staff_only=False,
    ).count() >= 10:
        return JsonResponse({'error': 'Rate limit exceeded. Max 10 reports per hour.'}, status=429)

    if content_type == 'post':
        post_id = request.POST.get('post_id')
        post = get_object_or_404(Post, id=post_id)
        # Prevent duplicate reports
        if Report.objects.filter(reporter=request.user, post=post, status='pending').exists():
            return JsonResponse({'error': 'You already reported this post.'}, status=400)
        Report.objects.create(
            reporter=request.user,
            content_type='post',
            post=post,
            report_type=report_type,
            description=description,
        )
    elif content_type == 'comment':
        comment_id = request.POST.get('comment_id')
        comment = get_object_or_404(Comment, id=comment_id)
        if Report.objects.filter(reporter=request.user, comment=comment, status='pending').exists():
            return JsonResponse({'error': 'You already reported this comment.'}, status=400)
        Report.objects.create(
            reporter=request.user,
            content_type='comment',
            comment=comment,
            post=comment.post,  # link to parent post so stage mod queues can find it
            report_type=report_type,
            description=description,
        )
    else:
        return JsonResponse({'error': 'Invalid content type.'}, status=400)

    return JsonResponse({'success': True, 'message': 'Report submitted. Thanks!'})


def search(request):
    """Search posts, users, and stages."""
    query = request.GET.get('q', '').strip()
    results = {'posts': [], 'users': [], 'stages': []}

    if query and len(query) >= 2:
        results['posts'] = Post.objects.filter(
            Q(title__icontains=query) | Q(body__icontains=query),
            is_published=True, is_blocked=False
        ).select_related('author', 'stage').prefetch_related('images').order_by('-created_at')[:20]

        results['users'] = User.objects.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query),
            is_active=True
        ).select_related('profile').order_by('-date_joined')[:10]

        results['stages'] = Stage.objects.filter(
            Q(name__icontains=query) | Q(title__icontains=query) | Q(description__icontains=query),
            is_active=True
        )[:10]

    sidebar_stages = Stage.objects.filter(is_active=True).order_by('-members_count')[:14]

    # Pre-search discovery content (only when no query)
    trending_posts = []
    top_stages = []
    if not query:
        trending_posts = Post.objects.filter(
            is_published=True, is_blocked=False
        ).annotate(
            title_len=Length('title')
        ).filter(
            title_len__gte=15,
            view_count__gte=2,
        ).select_related('author', 'stage').prefetch_related('images').order_by('-view_count')[:5]

        # Show stages user hasn't joined yet (or all for anon)
        top_qs = Stage.objects.filter(is_active=True)
        if request.user.is_authenticated:
            top_qs = top_qs.exclude(members=request.user)
        top_stages = top_qs.order_by('-members_count')[:8]

    return render(request, 'search.html', {
        'query': query,
        'results': results,
        'stages': sidebar_stages,
        'trending_posts': trending_posts,
        'top_stages': top_stages,
    })


@login_required(login_url='/users/login/')
@require_POST
def toggle_bookmark(request, post_id):
    """Toggle bookmark on a post via AJAX."""
    post = get_object_or_404(Post, id=post_id)
    deleted, _ = Bookmark.objects.filter(user=request.user, post=post).delete()
    if deleted:
        return JsonResponse({'bookmarked': False})
    Bookmark.objects.create(user=request.user, post=post)
    return JsonResponse({'bookmarked': True})


@login_required(login_url='/users/login/')
def saved_posts(request):
    """View all bookmarked/saved posts."""
    bookmarks = Bookmark.objects.filter(user=request.user).select_related(
        'post', 'post__author', 'post__stage'
    ).prefetch_related('post__images').annotate(
        post_like_count=Count('post__likes', distinct=True),
        post_comment_count=Count('post__comments', distinct=True),
    )

    paginator = Paginator(bookmarks, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'posts/saved.html', {
        'page_obj': page_obj,
        'view_type': 'saved',
    })
