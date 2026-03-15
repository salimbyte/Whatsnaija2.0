from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from django.core.paginator import Paginator
from django.db.models import Q

from .models import Report, ModAction
from posts.models import Post
from stages.models import Stage, StageModerator
from django.contrib.auth import get_user_model
from django.utils import timezone

from vaze.utils import send_notification, clean_reason, ban_until_from_key

User = get_user_model()


def staff_required(view_func):
    """Decorator that checks if user is staff."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/users/login/?next={request.path}')
        if not request.user.is_staff:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _strict_staff(view_func):
    """Restrict to Django staff only."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Staff access required.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@staff_required
def dashboard(request):
    """Moderation dashboard overview."""
    pending_count = Report.objects.filter(status='pending').count()

    pending_reports = Report.objects.filter(status='pending').select_related(
        'reporter', 'post', 'comment', 'post__author', 'comment__user'
    )[:20]
    recent_actions = ModAction.objects.select_related(
        'moderator', 'target_user', 'target_post'
    ).order_by('-created_at')[:15]

    stats = {
        'pending_reports': pending_count,
        'total_reports': Report.objects.count(),
        'blocked_posts': Post.objects.filter(is_blocked=True).count(),
        'total_users': User.objects.filter(is_active=True).count(),
        'banned_users': User.objects.filter(is_active=False).count(),
        'total_stages': Stage.objects.filter(is_active=True).count(),
    }
    return render(request, 'moderations/dashboard.html', {
        'pending_reports': pending_reports,
        'recent_actions': recent_actions,
        'stats': stats,
        'nav_pending': pending_count,
    })


@login_required
@staff_required
def stages_manage(request):
    """Stage management for staff."""
    pending_count = Report.objects.filter(status='pending').count()
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    stages_qs = Stage.objects.order_by('-members_count', 'name')
    if q:
        stages_qs = stages_qs.filter(
            Q(name__icontains=q) | Q(title__icontains=q)
        )
    if status_filter == 'active':
        stages_qs = stages_qs.filter(is_active=True)
    elif status_filter == 'disabled':
        stages_qs = stages_qs.filter(is_active=False)

    paginator = Paginator(stages_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    stages_list = stages_qs.only('id', 'name', 'title', 'is_active', 'members_count')
    return render(request, 'moderations/stages_manage.html', {
        'nav_pending': pending_count,
        'stages_list': stages_list,
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
    })


@login_required
@staff_required
@require_POST
def assign_stage_moderator(request):
    """Assign a moderator to a stage (staff only)."""
    stage_id = request.POST.get('stage_id')
    username = (request.POST.get('username') or '').strip()
    if not stage_id or not username:
        messages.error(request, 'Stage and username are required.')
        return redirect('moderations:dashboard')

    stage = get_object_or_404(Stage, id=stage_id)
    target = get_object_or_404(User, username__iexact=username)

    mod, created = StageModerator.objects.get_or_create(
        user=target, stage=stage,
        defaults={'added_by': request.user, 'is_active': True, 'is_super_mod': False},
    )
    if not created:
        if mod.is_active:
            messages.info(request, f'{target.username} is already a moderator for s/{stage.name}.')
        else:
            mod.is_active = True
            mod.added_by = request.user
            mod.save()
            messages.success(request, f'{target.username} reactivated as moderator for s/{stage.name}.')
    else:
        messages.success(request, f'{target.username} added as moderator for s/{stage.name}.')

    ModAction.objects.create(
        moderator=request.user, action='add_mod',
        target_user=target, stage=stage,
        reason=f'Assigned moderator in s/{stage.name}',
    )
    send_notification(
        recipient=target,
        sender=request.user,
        notification_type='mod_add',
        text=f'You have been added as a moderator for s/{stage.name}.',
        link=f'/s/{stage.name}/mod/',
    )
    return redirect('moderations:stages_manage')


@login_required
@staff_required
@require_POST
def remove_stage_moderator(request):
    """Remove a moderator from a stage (staff only)."""
    stage_id = request.POST.get('stage_id')
    username = (request.POST.get('username') or '').strip()
    if not stage_id or not username:
        messages.error(request, 'Stage and username are required.')
        return redirect('moderations:stages_manage')

    stage = get_object_or_404(Stage, id=stage_id)
    target = get_object_or_404(User, username__iexact=username)

    mod = StageModerator.objects.filter(
        user=target, stage=stage, is_active=True
    ).first()
    if not mod:
        messages.info(request, f'{target.username} is not an active moderator for s/{stage.name}.')
        return redirect('moderations:stages_manage')

    mod.is_active = False
    mod.save(update_fields=['is_active'])

    ModAction.objects.create(
        moderator=request.user, action='remove_mod',
        target_user=target, stage=stage,
        reason=f'Removed moderator in s/{stage.name}',
    )
    send_notification(
        recipient=target,
        sender=request.user,
        notification_type='mod_remove',
        text=f'You have been removed as a moderator for s/{stage.name}.',
        link='/',
    )
    messages.success(request, f'{target.username} removed from moderators in s/{stage.name}.')
    return redirect('moderations:stages_manage')


@login_required
@staff_required
@require_POST
def toggle_stage_active(request, stage_id):
    """Enable/disable a stage (staff only)."""
    stage = get_object_or_404(Stage, id=stage_id)
    stage.is_active = not stage.is_active
    stage.save(update_fields=['is_active'])

    action = 'enable_stage' if stage.is_active else 'disable_stage'
    ModAction.objects.create(
        moderator=request.user, action=action,
        stage=stage,
        reason=f'{"Enabled" if stage.is_active else "Disabled"} s/{stage.name}',
    )
    messages.success(
        request,
        f's/{stage.name} {"enabled" if stage.is_active else "disabled"}.'
    )
    return redirect('moderations:stages_manage')


@login_required
@staff_required
def report_queue(request):
    """View all pending reports."""
    status_filter = request.GET.get('status', 'pending')
    reports = Report.objects.select_related(
        'reporter', 'post', 'comment', 'post__author', 'comment__user', 'reviewed_by'
    ).order_by('-created_at')
    if status_filter != 'all':
        reports = reports.filter(status=status_filter)

    paginator = Paginator(reports, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    nav_pending = Report.objects.filter(status='pending').count()

    return render(request, 'moderations/reports.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'nav_pending': nav_pending,
    })


@login_required
@staff_required
@require_POST
def resolve_report(request, report_id):
    """Resolve a report with an action."""
    report = get_object_or_404(Report, id=report_id)

    if report.status != 'pending':
        messages.info(request, 'This report has already been resolved.')
        return redirect('moderations:report_queue')

    action = request.POST.get('action')
    public_reason = request.POST.get('public_reason', '').strip()[:200]
    if not public_reason:
        public_reason = request.POST.get('reason', '').strip()[:200]
    mod_note = request.POST.get('mod_note', '').strip()[:500]

    if action == 'dismiss':
        report.status = 'dismissed'
        report.reviewed_by = request.user
        report.mod_note = mod_note
        report.public_reason = public_reason
        report.save()
        ModAction.objects.create(
            moderator=request.user,
            action='dismiss_report',
            reason=public_reason or mod_note or f'Dismissed report #{report.id}',
        )
    elif action == 'block_post' and report.post:
        report.post.is_blocked = True
        report.post.save()
        report.status = 'action_taken'
        report.reviewed_by = request.user
        report.mod_note = mod_note
        report.public_reason = public_reason
        report.save()
        ModAction.objects.create(
            moderator=request.user,
            action='block_post',
            target_post=report.post,
            target_user=report.post.author,
            reason=public_reason or mod_note or f'Blocked post: {report.post.title}',
        )
        if report.post.author:
            send_notification(
                recipient=report.post.author,
                sender=None,
                notification_type='post_removed',
                text=(
                    f'Your post "{report.post.title[:60]}" was removed by platform moderation.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                ),
                link='/',
            )
    elif action == 'delete_post' and report.post:
        post_author = report.post.author
        post_title = report.post.title
        # Save report status BEFORE deleting the post — post deletion would
        # previously cascade-delete this report (now SET_NULL, but order still matters)
        report.status = 'action_taken'
        report.reviewed_by = request.user
        report.mod_note = mod_note
        report.public_reason = public_reason
        report.save()
        ModAction.objects.create(
            moderator=request.user,
            action='delete_post',
            target_user=post_author,
            reason=public_reason or mod_note or f'Deleted post: {post_title}',
        )
        if post_author:
            send_notification(
                recipient=post_author,
                sender=None,
                notification_type='post_removed',
                text=(
                    f'Your post "{post_title[:60]}" was deleted by platform moderation.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                ),
                link='/',
            )
        report.post.delete()
    elif action == 'delete_comment' and report.comment:
        comment_user = report.comment.user
        # Save report status BEFORE deleting the comment
        report.status = 'action_taken'
        report.reviewed_by = request.user
        report.mod_note = mod_note
        report.public_reason = public_reason
        report.save()
        ModAction.objects.create(
            moderator=request.user,
            action='delete_comment',
            target_user=comment_user,
            reason=public_reason or mod_note or f'Deleted comment #{report.comment.id}',
        )
        if comment_user:
            send_notification(
                recipient=comment_user,
                sender=None,
                notification_type='post_removed',
                text=(
                    'Your comment was removed by platform moderation.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                ),
                link='/',
            )
        report.comment.delete()
    elif action == 'ban_user':
        if not request.user.is_staff:
            messages.error(request, 'Only staff can issue site-wide bans.')
            return redirect('moderations:report_queue')
        target = report.post.author if report.post else (report.comment.user if report.comment else None)
        if not target:
            messages.error(request, 'Could not find the target user for this report.')
            return redirect('moderations:report_queue')
        if target.is_staff or target.is_superuser:
            messages.error(request, 'Cannot ban staff users.')
            return redirect('moderations:report_queue')
        duration_key = request.POST.get('ban_duration')
        ban_until = ban_until_from_key(duration_key)
        target.is_active = False
        target.ban_until = ban_until
        target.save()
        report.status = 'action_taken'
        report.reviewed_by = request.user
        report.mod_note = mod_note
        report.public_reason = public_reason
        report.save()
        ModAction.objects.create(
            moderator=request.user,
            action='ban_user',
            target_user=target,
            reason=public_reason or mod_note or f'Banned user: {target.username}',
        )
        until_msg = (
            f' Ban ends {timezone.localtime(ban_until).strftime("%b %d, %Y %H:%M")}. '
            if ban_until else ''
        )
        send_notification(
            recipient=target,
            sender=None,
            notification_type='stage_ban',
            text=(
                'Your account has been suspended by platform moderation.'
                + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                + (f' {until_msg.strip()}' if until_msg else '')
            ),
            link='/',
        )
    else:
        messages.error(request, 'Invalid action or the reported content no longer exists.')
        return redirect('moderations:report_queue')

    messages.success(request, 'Report resolved.')
    return redirect('moderations:report_queue')


@login_required
@staff_required
@require_POST
def toggle_block_post(request, post_id):
    """Toggle post blocked status via AJAX."""
    post = get_object_or_404(Post, id=post_id)
    post.is_blocked = not post.is_blocked
    post.save()

    action = 'block_post' if post.is_blocked else 'unblock_post'
    ModAction.objects.create(
        moderator=request.user,
        action=action,
        target_post=post,
        target_user=post.author,
        reason=f'{"Blocked" if post.is_blocked else "Unblocked"} post: {post.title}',
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'is_blocked': post.is_blocked, 'action': action})
    messages.success(request, f'Post {"blocked" if post.is_blocked else "unblocked"}.')
    return redirect(request.POST.get('next', 'moderations:blocked_posts'))


@login_required
@_strict_staff
@require_POST
def toggle_ban_user(request, user_id):
    """Toggle user active status (ban/unban)."""
    target = get_object_or_404(User, id=user_id)
    if target.is_staff or target.is_superuser:
        messages.error(request, 'Cannot ban staff users.')
        return redirect(request.POST.get('next', 'moderations:users_list'))

    public_reason = request.POST.get('public_reason', '').strip()[:200]
    if not public_reason:
        public_reason = request.POST.get('reason', '').strip()[:200]

    if target.is_active:
        duration_key = request.POST.get('ban_duration')
        target.ban_until = ban_until_from_key(duration_key)
        target.is_active = False
    else:
        target.is_active = True
        target.ban_until = None
    target.save()

    action = 'ban_user' if not target.is_active else 'unban_user'
    ModAction.objects.create(
        moderator=request.user,
        action=action,
        target_user=target,
        reason=public_reason or f'{"Banned" if not target.is_active else "Unbanned"} user: {target.username}',
    )
    # Notify the affected user
    if not target.is_active:
        until_msg = (
            f' Ban ends {timezone.localtime(target.ban_until).strftime("%b %d, %Y %H:%M")}. '
            if target.ban_until else ''
        )
        send_notification(
            recipient=target,
            sender=None,
            notification_type='stage_ban',
            text=(
                'Your account has been suspended by platform moderation.'
                + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                + (f' {until_msg.strip()}' if until_msg else '')
            ),
            link='/',
        )
    else:
        send_notification(
            recipient=target,
            sender=None,
            notification_type='stage_unban',
            text='Your account suspension has been lifted. Welcome back.',
            link='/',
        )

    messages.success(request, f'User {"banned" if not target.is_active else "unbanned"}.')
    return redirect(request.POST.get('next', 'moderations:users_list'))


# ───────────────────────────────────────────────────────────
#  User management
# ───────────────────────────────────────────────────────────

@login_required
@staff_required
def users_list(request):
    """Search, filter and manage user accounts."""
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')

    users_qs = User.objects.select_related('profile').order_by('-date_joined')

    if q:
        users_qs = users_qs.filter(Q(username__icontains=q) | Q(email__icontains=q))

    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'banned':
        users_qs = users_qs.filter(is_active=False)
    elif status_filter == 'staff':
        users_qs = users_qs.filter(is_staff=True)

    paginator = Paginator(users_qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'moderations/users_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'nav_pending': Report.objects.filter(status='pending').count(),
    })


# ───────────────────────────────────────────────────────────
#  Blocked posts list
# ───────────────────────────────────────────────────────────

@login_required
@staff_required
def blocked_posts(request):
    """List all platform-blocked posts with option to restore."""
    posts_qs = Post.objects.filter(is_blocked=True).select_related(
        'author', 'stage'
    ).order_by('-updated_at')

    paginator = Paginator(posts_qs, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'moderations/blocked_posts.html', {
        'page_obj': page_obj,
        'nav_pending': Report.objects.filter(status='pending').count(),
    })


@login_required
def appeal(request):
    """Submit an appeal to staff about a moderation decision."""
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()[:500]
        if not message:
            messages.error(request, 'Please provide details for your appeal.')
            return redirect(request.path)

        context_type = request.POST.get('context_type', '').strip()[:50]
        source_id = request.POST.get('source_id', '').strip()[:50]
        context_link = request.POST.get('context_link', '').strip()[:500]
        context_note = request.POST.get('context_note', '').strip()[:200]

        note_parts = []
        if context_type:
            note_parts.append(f'type={context_type}')
        if source_id:
            note_parts.append(f'source={source_id}')
        if context_link:
            note_parts.append(f'link={context_link}')
        if context_note:
            note_parts.append(f'note={context_note}')
        mod_note = f"Appeal context: {'; '.join(note_parts)}" if note_parts else ''

        Report.objects.create(
            reporter=request.user,
            content_type='appeal',
            report_type='appeal',
            description=message,
            mod_note=mod_note[:500],
            staff_only=True,
        )
        messages.success(request, 'Appeal submitted. A staff member will review it.')
        return redirect('/users/notifications/')

    return render(request, 'moderations/appeal.html', {
        'appeal_type': request.GET.get('type', '').strip(),
        'context_link': request.GET.get('link', '').strip(),
        'source_id': request.GET.get('source', '').strip(),
    })

