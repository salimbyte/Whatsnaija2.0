from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from django.utils import timezone

from stages.models import Stage, StageModerator, StageBan, CATEGORY_ORDER, CATEGORY_META
from stages.forms import StageForm
from stages.mod_utils import can_moderate_stage, can_assign_mods, mod_required
from posts.models import Post
from moderations.models import Report, ModAction
from vaze.utils import send_notification, clean_reason, ban_until_from_key

User = get_user_model()


def _active_stage_ban_qs():
    now = timezone.now()
    StageBan.objects.filter(is_active=True, expires_at__lt=now).update(is_active=False)
    return StageBan.objects.filter(is_active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def _active_stage_ban(user, stage):
    if not user or not stage:
        return None
    return _active_stage_ban_qs().filter(user=user, stage=stage).first()


def stages_list(request):
    """Browse all active stages grouped by category with live search."""
    stages = list(
        Stage.objects.filter(is_active=True).annotate(
            post_count=Count('posts', filter=Q(posts__is_published=True), distinct=True),
        ).order_by('category', '-members_count', 'name')
    )

    is_member_map = {}
    if request.user.is_authenticated:
        joined_ids = set(request.user.joined_stages.values_list('pk', flat=True))
        is_member_map = {s.pk: (s.pk in joined_ids) for s in stages}

    # Build ordered category groups: [(label, icon, [stages]), ...]
    grouped_stages = []
    for cat_key in CATEGORY_ORDER:
        label, icon = CATEGORY_META[cat_key]
        cat_stages = [s for s in stages if s.category == cat_key]
        if cat_stages:
            grouped_stages.append((label, icon, cat_stages))

    return render(request, 'stages/stages.html', {
        'stages': stages,
        'grouped_stages': grouped_stages,
        'is_member_map': is_member_map,
    })


def stage_page(request, stage_name):
    """Display a stage with its posts"""
    stage = get_object_or_404(Stage, name=stage_name)
    
    # Get all stages for sidebar
    all_stages = Stage.objects.filter(is_active=True).order_by('-members_count')[:30]
    
    # Get posts for this stage — annotate comment count instead of prefetching all comments
    posts = Post.objects.filter(
        stage=stage, is_published=True, is_blocked=False
    ).select_related('author', 'stage').prefetch_related('images').annotate(
        comment_count=Count('comments', distinct=True),
        like_count=Count('likes', distinct=True)
    )
    
    # Get sorting parameter — default to popular (Hot) for consistency with homepage
    sort_by = request.GET.get('sort', 'popular')
    
    if sort_by == 'popular' or sort_by == 'top':
        posts = posts.order_by('-like_count', '-created_at')
    else:  # new
        posts = posts.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    active_ban = _active_stage_ban(request.user, stage) if request.user.is_authenticated else None
    context = {
        "stage": stage,
        "posts": page_obj,
        "post_count": paginator.count,
        "sort_by": sort_by,
        "all_stages": all_stages,
        "is_mod": can_moderate_stage(request.user, stage) if request.user.is_authenticated else False,
        "can_assign_mods": can_assign_mods(request.user, stage) if request.user.is_authenticated else False,
        "is_member": stage.members.filter(pk=request.user.pk).exists() if request.user.is_authenticated else False,
        "is_banned": bool(active_ban),
        "active_ban": active_ban,
        "stage_mods": StageModerator.objects.filter(stage=stage, is_active=True, is_super_mod=False).select_related('user__profile').order_by('created_at'),
    }
    
    return render(request, "stages/stage.html", context)


@login_required(login_url='/users/login/')
@require_POST
def join_stage(request, stage_name):
    """Toggle membership of the current user in a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    user = request.user
    if stage.members.filter(pk=user.pk).exists():
        stage.members.remove(user)
        # Decrement via F() to avoid races; floor at 0
        Stage.objects.filter(pk=stage.pk, members_count__gt=0).update(
            members_count=F('members_count') - 1
        )
        joined = False
    else:
        stage.members.add(user)
        Stage.objects.filter(pk=stage.pk).update(members_count=F('members_count') + 1)
        joined = True
    stage.refresh_from_db(fields=['members_count'])
    return JsonResponse({'joined': joined, 'members_count': stage.members_count})


@login_required(login_url='/users/login/')
def my_mod_overview(request):
    """Overview of all stages this user moderates — landing page for the nav shield icon."""
    from moderations.models import Report

    # Platform staff/super-mods → full platform dashboard
    if request.user.is_staff:
        return redirect('moderations:dashboard')
    from stages.mod_utils import is_platform_super_mod
    if is_platform_super_mod(request.user):
        return redirect('moderations:dashboard')

    mod_records = StageModerator.objects.filter(
        user=request.user, is_active=True
    ).select_related('stage').annotate(
        pending_count=Count(
            'stage__posts__reports',
            filter=Q(stage__posts__reports__status='pending'),
            distinct=True,
        )
    ).order_by('stage__name')

    if not mod_records.exists():
        messages.info(request, "You don't have any moderation roles.")
        return redirect('/')

    stages_data = [{'mod': rec, 'pending': rec.pending_count} for rec in mod_records]

    return render(request, 'stages/my_mod_overview.html', {'stages_data': stages_data})


@login_required(login_url='/users/login/')
def create_stage(request):
    """Create a new stage/community. Staff only."""
    if not request.user.is_staff:
        messages.error(request, "Only staff can create stages.")
        return redirect('popular')
    if request.method == 'POST':
        form = StageForm(request.POST, request.FILES)
        if form.is_valid():
            stage = form.save(commit=False)
            stage.admin = request.user
            stage.save()
            messages.success(request, f"Community s/{stage.name} created!")
            return redirect('stages:stage_page', stage_name=stage.name)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StageForm()

    return render(request, 'stages/create.html', {'form': form})


@login_required(login_url='/users/login/')
def edit_stage(request, stage_name):
    """Edit an existing stage (admin or staff only)."""
    stage = get_object_or_404(Stage, name=stage_name)

    if request.user != stage.admin and not request.user.is_staff:
        messages.error(request, "You don't have permission to edit this community.")
        return redirect('stages:stage_page', stage_name=stage.name)

    if request.method == 'POST':
        form = StageForm(request.POST, request.FILES, instance=stage)
        if form.is_valid():
            form.save()
            messages.success(request, "Community updated!")
            return redirect('stages:stage_page', stage_name=stage.name)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StageForm(instance=stage)

    return render(request, 'stages/edit.html', {'form': form, 'stage': stage})


# ═══════════════════════════════════════════════════════════
#   STAGE MODERATION VIEWS
# ═══════════════════════════════════════════════════════════

def _mod_context(request, stage):
    """Build common moderation context dict."""
    return {
        'stage': stage,
        'is_mod': True,
        'can_assign': can_assign_mods(request.user, stage),
        'pending_count': Report.objects.filter(
            post__stage=stage, status='pending', staff_only=False
        ).count(),
        'active_mods': StageModerator.objects.filter(
            stage=stage, is_active=True, is_super_mod=False
        ).select_related('user').order_by('created_at'),
        'banned_count': _active_stage_ban_qs().filter(stage=stage).count(),
    }


@login_required(login_url='/users/login/')
@mod_required
def mod_dashboard(request, stage_name):
    """Main moderation dashboard for a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    ctx = _mod_context(request, stage)

    ctx['pending_reports'] = Report.objects.filter(
        post__stage=stage, status='pending', staff_only=False
    ).select_related('reporter', 'post', 'post__author')[:10]

    ctx['recent_actions'] = ModAction.objects.filter(
        stage=stage
    ).select_related('moderator', 'target_user', 'target_post').order_by('-created_at')[:10]

    ctx['stats'] = {
        'pending': ctx['pending_count'],  # reuse value already fetched by _mod_context
        'total_reports': Report.objects.filter(post__stage=stage, staff_only=False).count(),
        'blocked_posts': Post.objects.filter(stage=stage, is_blocked=True).count(),
        'active_mods': StageModerator.objects.filter(stage=stage, is_active=True, is_super_mod=False).count(),
        'bans': _active_stage_ban_qs().filter(stage=stage).count(),
    }

    return render(request, 'stages/mod_dashboard.html', ctx)


@login_required(login_url='/users/login/')
@mod_required
def mod_queue(request, stage_name):
    """Report queue for a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    status_filter = request.GET.get('status', 'pending')

    reports = Report.objects.filter(post__stage=stage, staff_only=False).select_related(
        'reporter', 'post', 'post__author', 'comment', 'reviewed_by'
    )
    if status_filter != 'all':
        reports = reports.filter(status=status_filter)
    reports = reports.order_by('-created_at')

    paginator = Paginator(reports, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    ctx = _mod_context(request, stage)
    ctx['reports'] = page_obj
    ctx['page_obj'] = page_obj
    ctx['status_filter'] = status_filter
    return render(request, 'stages/mod_queue.html', ctx)


@login_required(login_url='/users/login/')
@mod_required
@require_POST
def mod_resolve_report(request, stage_name, report_id):
    """Resolve a report in this stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    report = get_object_or_404(Report, id=report_id, post__stage=stage)

    if report.status != 'pending':
        messages.info(request, 'This report has already been resolved.')
        return redirect('stages:mod_queue', stage_name=stage.name)

    action = request.POST.get('action', '').strip()
    public_reason = request.POST.get('public_reason', '').strip()[:200]
    if not public_reason:
        public_reason = request.POST.get('reason', '').strip()[:200]
    mod_note = request.POST.get('mod_note', '').strip()[:500]

    report.reviewed_by = request.user
    report.mod_note = mod_note
    report.public_reason = public_reason

    if action == 'dismiss':
        report.status = 'dismissed'
        report.save()
        ModAction.objects.create(
            moderator=request.user, action='dismiss_report',
            stage=stage, reason=public_reason or mod_note or f'Dismissed report #{report.id}',
        )
        messages.success(request, 'Report dismissed.')

    elif action == 'remove_post' and report.post:
        report.post.is_blocked = True
        report.post.save()
        report.status = 'action_taken'
        report.save()
        ModAction.objects.create(
            moderator=request.user, action='block_post',
            target_post=report.post, target_user=report.post.author,
            stage=stage, reason=public_reason or mod_note or f'Removed post via report #{report.id}',
        )
        # Notify post author
        if report.post.author:
            send_notification(
                recipient=report.post.author,
                sender=None,
                notification_type='post_removed',
                text=(
                    f'Your post "{report.post.title[:60]}" was removed by a moderator in s/{stage.name}.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                ),
                link=f'/s/{stage.name}/',
            )
        messages.success(request, 'Post removed.')

    elif action == 'delete_comment' and report.comment:
        comment_user = report.comment.user
        report.status = 'action_taken'
        report.save()
        ModAction.objects.create(
            moderator=request.user, action='delete_comment',
            target_user=comment_user, stage=stage,
            reason=public_reason or mod_note or f'Deleted comment via report #{report.id}',
        )
        if comment_user:
            send_notification(
                recipient=comment_user,
                sender=None,
                notification_type='post_removed',
                text=(
                    f'Your comment was removed by a moderator in s/{stage.name}.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                ),
                link=f'/s/{stage.name}/',
            )
        report.comment.delete()
        messages.success(request, 'Comment deleted.')

    elif action == 'ban_user':
        target = report.post.author if report.post else (
            report.comment.user if report.comment else None
        )
        if target and (
            target == stage.admin or target.is_staff
            or StageModerator.objects.filter(user=target, stage=stage, is_active=True).exists()
        ):
            messages.error(request, f'Cannot ban {target.username} — they are a moderator or admin. Remove their mod role first.')
        elif target:
            duration_key = request.POST.get('ban_duration')
            expires_at = ban_until_from_key(duration_key)
            ban, created = StageBan.objects.get_or_create(
                user=target, stage=stage,
                defaults={
                    'banned_by': request.user,
                    'reason': public_reason,
                    'expires_at': expires_at,
                    'is_active': True,
                },
            )
            if not created:
                ban.is_active = True
                ban.banned_by = request.user
                ban.reason = public_reason
                ban.expires_at = expires_at
                ban.save()
            report.status = 'action_taken'
            report.save()
            ModAction.objects.create(
                moderator=request.user, action='stage_ban',
                target_user=target, stage=stage,
                reason=public_reason or mod_note or f'Stage banned via report #{report.id}',
            )
            until_msg = (
                f' Ban ends {timezone.localtime(expires_at).strftime("%b %d, %Y %H:%M")}. '
                if expires_at else ''
            )
            # Notify banned user
            send_notification(
                recipient=target,
                sender=None,
                notification_type='stage_ban',
                text=(
                    f'You have been banned from s/{stage.name}.'
                    + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
                    + (f' {until_msg.strip()}' if until_msg else '')
                ),
                link=f'/s/{stage.name}/',
            )
            messages.success(request, f'{target.username} banned from s/{stage.name}.')
        else:
            messages.error(request, 'Could not find target user.')

    else:
        messages.error(request, 'Invalid action or the reported content no longer exists.')

    return redirect('stages:mod_queue', stage_name=stage.name)


@login_required(login_url='/users/login/')
@mod_required
@require_POST
def mod_remove_post(request, stage_name, post_id):
    """Toggle block status on a post in this stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    post = get_object_or_404(Post, id=post_id, stage=stage)
    public_reason = request.POST.get('public_reason', '').strip()[:200]
    legacy_reason = request.POST.get('reason', '').strip()[:200]
    mod_note = request.POST.get('mod_note', '').strip()[:500]
    reason = public_reason or legacy_reason

    post.is_blocked = not post.is_blocked
    post.save()

    action_key = 'block_post' if post.is_blocked else 'unblock_post'
    ModAction.objects.create(
        moderator=request.user, action=action_key,
        target_post=post, target_user=post.author,
        stage=stage, reason=reason or mod_note or f'{"Removed" if post.is_blocked else "Restored"} post: {post.title}',
    )
    # Notify post author when their post is removed (not when restored)
    if post.is_blocked and post.author:
        send_notification(
            recipient=post.author,
            sender=None,
            notification_type='post_removed',
            text=(
                f'Your post "{post.title[:60]}" was removed by a moderator in s/{stage.name}.'
                + (f' Reason: {clean_reason(reason)}' if clean_reason(reason) else '')
            ),
            link=f'/s/{stage.name}/',
        )
    label = 'removed' if post.is_blocked else 'restored'
    messages.success(request, f'Post {label}.')
    return redirect(request.POST.get('next', f'/s/{stage.name}/'))


@login_required(login_url='/users/login/')
@mod_required
@require_POST
def mod_ban_user(request, stage_name):
    """Ban a user from a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    username = request.POST.get('username', '').strip()
    public_reason = request.POST.get('public_reason', '').strip()[:200]
    if not public_reason:
        public_reason = request.POST.get('reason', '').strip()[:200]
    mod_note = request.POST.get('mod_note', '').strip()[:500]

    target = get_object_or_404(User, username__iexact=username)

    is_target_mod = StageModerator.objects.filter(
        user=target, stage=stage, is_active=True, is_super_mod=False
    ).exists()
    if target == stage.admin or target.is_staff or is_target_mod:
        messages.error(request, "Cannot ban a stage admin, staff, or active moderator. Remove their mod role first.")
        return redirect('stages:mod_members', stage_name=stage.name)

    duration_key = request.POST.get('ban_duration')
    expires_at = ban_until_from_key(duration_key)
    ban, created = StageBan.objects.get_or_create(
        user=target, stage=stage,
        defaults={
            'banned_by': request.user,
            'reason': public_reason,
            'expires_at': expires_at,
            'is_active': True,
        },
    )
    if not created:
        ban.is_active = True
        ban.banned_by = request.user
        ban.reason = public_reason
        ban.expires_at = expires_at
        ban.save()

    ModAction.objects.create(
        moderator=request.user, action='stage_ban',
        target_user=target, stage=stage,
        reason=public_reason or mod_note or f'Stage banned {target.username}',
    )
    until_msg = (
        f' Ban ends {timezone.localtime(expires_at).strftime("%b %d, %Y %H:%M")}. '
        if expires_at else ''
    )
    # Notify banned user
    send_notification(
        recipient=target,
        sender=None,
        notification_type='stage_ban',
        text=(
            f'You have been banned from s/{stage.name}.'
            + (f' Reason: {clean_reason(public_reason)}' if clean_reason(public_reason) else '')
            + (f' {until_msg.strip()}' if until_msg else '')
        ),
        link=f'/s/{stage.name}/',
    )
    messages.success(request, f'{target.username} has been banned from s/{stage.name}.')
    return redirect('stages:mod_members', stage_name=stage.name)


@login_required(login_url='/users/login/')
@mod_required
@require_POST
def mod_unban_user(request, stage_name, ban_id):
    """Unban a user from a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    ban = get_object_or_404(StageBan, id=ban_id, stage=stage)
    ban.is_active = False
    ban.expires_at = None
    ban.save()

    ModAction.objects.create(
        moderator=request.user, action='stage_unban',
        target_user=ban.user, stage=stage,
        reason=f'Unbanned {ban.user.username}',
    )
    # Notify unbanned user
    send_notification(
        recipient=ban.user,
        sender=None,
        notification_type='stage_unban',
        text=f'Your ban from s/{stage.name} has been lifted.',
        link=f'/s/{stage.name}/',
    )
    messages.success(request, f'{ban.user.username} unbanned from s/{stage.name}.')
    return redirect('stages:mod_members', stage_name=stage.name)


@login_required(login_url='/users/login/')
@mod_required
def mod_members(request, stage_name):
    """Manage moderators and banned users for a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    ctx = _mod_context(request, stage)
    ctx['mods'] = StageModerator.objects.filter(
        stage=stage, is_active=True, is_super_mod=False
    ).select_related('user', 'added_by').order_by('created_at')
    ctx['bans'] = _active_stage_ban_qs().filter(
        stage=stage
    ).select_related('user', 'banned_by').order_by('-created_at')
    return render(request, 'stages/mod_members.html', ctx)


@login_required(login_url='/users/login/')
@require_POST
def mod_add_moderator(request, stage_name):
    """Add a user as moderator of this stage (stage admin/staff only)."""
    stage = get_object_or_404(Stage, name=stage_name)

    if not can_assign_mods(request.user, stage):
        messages.error(request, "Only the stage owner or staff can add moderators.")
        return redirect('stages:mod_members', stage_name=stage.name)

    username = request.POST.get('username', '').strip()
    target = get_object_or_404(User, username__iexact=username)

    if target == stage.admin:
        messages.error(request, f'{target.username} is already the stage owner.')
        return redirect('stages:mod_members', stage_name=stage.name)

    mod, created = StageModerator.objects.get_or_create(
        user=target, stage=stage,
        defaults={'added_by': request.user, 'is_active': True, 'is_super_mod': False},
    )
    if not created:
            if mod.is_active:
                messages.info(request, f'{target.username} is already a moderator.')
            else:
                mod.is_active = True
                mod.added_by = request.user
                mod.save()
                ModAction.objects.create(
                    moderator=request.user, action='add_mod',
                    target_user=target, stage=stage,
                    reason=f'Re-activated {target.username} as moderator of s/{stage.name}',
                )
                send_notification(
                    recipient=target,
                    sender=None,
                    notification_type='mod_add',
                    text=f'You have been re-added as a moderator of s/{stage.name}.',
                    link=f'/s/{stage.name}/mod/',
                )
                messages.success(request, f'{target.username} re-activated as moderator.')
    else:
        ModAction.objects.create(
            moderator=request.user, action='add_mod',
            target_user=target, stage=stage,
            reason=f'Added {target.username} as moderator of s/{stage.name}',
        )
        # Notify newly added mod
        send_notification(
            recipient=target,
            sender=None,
            notification_type='mod_add',
            text=f'You have been added as a moderator of s/{stage.name}.',
            link=f'/s/{stage.name}/mod/',
        )
        messages.success(request, f'{target.username} added as moderator of s/{stage.name}.')
    return redirect('stages:mod_members', stage_name=stage.name)


@login_required(login_url='/users/login/')
@require_POST
def mod_remove_moderator(request, stage_name, mod_id):
    """Remove a moderator from a stage."""
    stage = get_object_or_404(Stage, name=stage_name)

    if not can_assign_mods(request.user, stage):
        messages.error(request, "Only the stage owner or staff can remove moderators.")
        return redirect('stages:mod_members', stage_name=stage.name)

    mod = get_object_or_404(StageModerator, id=mod_id, stage=stage)
    target = mod.user
    mod.is_active = False
    mod.save()

    ModAction.objects.create(
        moderator=request.user, action='remove_mod',
        target_user=target, stage=stage,
        reason=f'Removed {target.username} as moderator of s/{stage.name}',
    )
    # Notify removed mod
    send_notification(
        recipient=target,
        sender=None,
        notification_type='mod_remove',
        text=f'You have been removed as a moderator of s/{stage.name}.',
        link=f'/s/{stage.name}/',
    )
    messages.success(request, f'{target.username} removed as moderator.')
    return redirect('stages:mod_members', stage_name=stage.name)


@login_required(login_url='/users/login/')
@mod_required
def mod_log(request, stage_name):
    """Moderation action log for a stage."""
    stage = get_object_or_404(Stage, name=stage_name)
    log = ModAction.objects.filter(stage=stage).select_related(
        'moderator', 'target_user', 'target_post'
    ).order_by('-created_at')

    paginator = Paginator(log, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    ctx = _mod_context(request, stage)
    ctx['log'] = page_obj
    return render(request, 'stages/mod_log.html', ctx)
