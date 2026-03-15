from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
from django.db.models import Q, Count, Exists, OuterRef, F
from django.db.models.functions import Lower
from django.core.paginator import Paginator

from django.core.cache import cache
from django.utils import timezone

from .forms import UserRegistrationForm, UserLoginForm, UserProfileForm, UserUpdateForm
from .models import UserProfile, Follow, Message, MessageReaction, is_reserved_username, ReservedUsername, USERNAME_MAX_LENGTH
from stages.models import Stage
from vaze.utils import send_notification

User = get_user_model()


def register(request):
    """
    Handles user registration with proper form validation.
    """
    if request.user.is_authenticated:
        return redirect('/')
    
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True
            user.save()
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("users:login")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = UserRegistrationForm()
    
    return render(request, "users/register.html", {"form": form})


def _username_suggestions(base: str, limit: int = 4):
    base = (base or "").strip()
    if not base:
        return []

    raw = [
        f"{base}ng",
        f"{base}hq",
        f"{base}official",
        f"{base}the",
        f"{base}_ng",
        f"{base}_hq",
        f"{base}_official",
        f"{base}1",
        f"{base}01",
        f"{base}123",
        f"{base}_1",
        f"{base}.1",
    ]
    for n in range(10, 40):
        raw.append(f"{base}{n}")

    candidates = []
    seen = set()
    for cand in raw:
        if len(cand) > USERNAME_MAX_LENGTH:
            continue
        lower = cand.lower()
        if lower in seen:
            continue
        seen.add(lower)
        candidates.append(cand)
        if len(candidates) >= 20:
            break

    if not candidates:
        return []

    lower_candidates = [c.lower() for c in candidates]
    taken = set(
        User.objects.annotate(u_lower=Lower('username'))
        .filter(u_lower__in=lower_candidates)
        .values_list('u_lower', flat=True)
    )
    reserved = set(
        ReservedUsername.objects.filter(name_lower__in=lower_candidates)
        .values_list('name_lower', flat=True)
    )
    available = [c for c in candidates if c.lower() not in taken and c.lower() not in reserved]
    return available[:limit]


def username_check(request):
    """
    AJAX: Check if a username is available.
    """
    username = (request.GET.get("username") or "").strip()
    if not username:
        return JsonResponse({"available": False, "reason": "empty"})

    if len(username) < 3:
        return JsonResponse({"available": False, "reason": "too_short"})
    if len(username) > USERNAME_MAX_LENGTH:
        return JsonResponse({"available": False, "reason": "too_long"})

    validator = UnicodeUsernameValidator()
    try:
        validator(username)
    except ValidationError:
        return JsonResponse({"available": False, "reason": "invalid"})

    if is_reserved_username(username):
        suggestions = _username_suggestions(username)
        return JsonResponse({"available": False, "reason": "reserved", "suggestions": suggestions})

    exists = User.objects.filter(username__iexact=username).exists()
    if exists:
        suggestions = _username_suggestions(username)
        return JsonResponse({"available": False, "reason": "taken", "suggestions": suggestions})

    return JsonResponse({"available": True, "reason": "available"})


def login_user(request):
    """
    Handles user authentication.
    """
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                next_url = request.GET.get('next', '/')
                return redirect(next_url)
        else:
            username = (request.POST.get('username') or '').strip()
            password = request.POST.get('password') or ''
            if username and password:
                try:
                    target = User.objects.get(username__iexact=username)
                except User.DoesNotExist:
                    target = None
                if target and not target.is_active and target.check_password(password):
                    if target.ban_until and target.ban_until <= timezone.now():
                        target.is_active = True
                        target.ban_until = None
                        target.save(update_fields=['is_active', 'ban_until'])
                        login(request, target)
                        messages.success(request, f"Welcome back, {target.username}!")
                        next_url = request.GET.get('next', '/')
                        return redirect(next_url)
                    if target.ban_until:
                        until = timezone.localtime(target.ban_until).strftime('%b %d, %Y %H:%M')
                        messages.error(request, f"Your account is suspended until {until}.")
                        return render(request, "users/login.html", {"form": form})
                    messages.error(request, "Your account is permanently suspended.")
                    return render(request, "users/login.html", {"form": form})
            messages.error(request, "Invalid username or password.")
    else:
        form = UserLoginForm()

    return render(request, "users/login.html", {"form": form})


@login_required
def logout_user(request):
    """
    Handles user logout.
    """
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("/")


def user(request, username):
    """
    Display user profile page.
    """
    user_obj = get_object_or_404(User, username=username)
    profile, _ = UserProfile.objects.get_or_create(user=user_obj)
    
    # Increment profile views (but not for the profile owner)
    if request.user != user_obj:
        UserProfile.objects.filter(pk=profile.pk).update(profile_views=F('profile_views') + 1)
    
    # Fetch all published posts, reuse the same queryset for both the list and count
    posts_qs = user_obj.posts.filter(is_published=True)
    posts_count = posts_qs.count()
    posts = posts_qs.select_related('stage', 'author').prefetch_related('images').annotate(
        comment_count=Count('comments', distinct=True),
        like_count=Count('likes', distinct=True)
    ).order_by('-created_at')[:20]
    comments = user_obj.comments.filter(is_anon=False).select_related('post').order_by('-created_at')[:40]

    # Fetch both follow counts in one annotated query instead of two COUNT queries
    user_counts = User.objects.filter(pk=user_obj.pk).annotate(
        followers_count=Count('followers', distinct=True),
        following_count=Count('following', distinct=True),
    ).values('followers_count', 'following_count').first()
    followers_count = user_counts['followers_count']
    following_count = user_counts['following_count']
    is_following = False
    mutual_followers = []
    if request.user.is_authenticated and request.user != user_obj:
        is_following = Follow.objects.filter(follower=request.user, following=user_obj).exists()
        user_following_ids = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        mutual_followers = list(
            Follow.objects.filter(following=user_obj, follower_id__in=user_following_ids)
            .select_related('follower', 'follower__profile')[:5]
        )

    active_stages = Stage.objects.filter(
        is_active=True,
        posts__author=user_obj,
        posts__is_published=True,
    ).only('name', 'title', 'image', 'members_count').distinct().order_by('-members_count')[:6]

    context = {
        'profile_user': user_obj,
        'profile': profile,
        'posts': posts,
        'posts_count': posts_count,
        'comments': comments,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'mutual_followers': mutual_followers,
        'active_stages': active_stages,
    }
    
    return render(request, "users/user.html", context)


@login_required
def edit_profile(request):
    """
    Edit user profile information.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(
            request.POST, 
            request.FILES, 
            instance=profile
        )
        
        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user_form.save()
                profile_form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profiles:user_profile', username=request.user.username)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'profile': profile,
    }
    
    return render(request, "users/edit.html", context)


@login_required
@require_POST
def toggle_follow(request, username):
    """Toggle follow/unfollow a user via AJAX."""
    target_user = get_object_or_404(User, username=username)

    if target_user == request.user:
        return JsonResponse({'error': 'You cannot follow yourself.'}, status=400)

    deleted_count, _ = Follow.objects.filter(follower=request.user, following=target_user).delete()
    if deleted_count:
        action = 'unfollowed'
    else:
        Follow.objects.create(follower=request.user, following=target_user)
        # Create notification
        send_notification(
            recipient=target_user,
            sender=request.user,
            notification_type='follow',
            text=f'{request.user.username} started following you',
            link=f'/{request.user.username}/',
        )
        action = 'followed'

    follower_count = target_user.followers.count()
    return JsonResponse({
        'action': action,
        'following': action == 'followed',
        'followers_count': follower_count,
    })


@login_required
def inbox(request):
    """Display message inbox with conversation threads."""
    search_query = request.GET.get('q', '').strip()

    conversations = {}
    msg_filter = Q(sender=request.user) | Q(recipient=request.user)
    # Cap at 500 most recent messages to prevent unbounded memory growth
    all_messages = Message.objects.filter(msg_filter).select_related(
        'sender', 'sender__profile', 'recipient', 'recipient__profile'
    ).order_by('-created_at')[:500]

    unread_counts = dict(
        Message.objects.filter(recipient=request.user, is_read=False)
        .values('sender')
        .annotate(count=Count('id'))
        .values_list('sender', 'count')
    )

    for msg in all_messages:
        other_user = msg.recipient if msg.sender == request.user else msg.sender
        if other_user.id not in conversations:
            conversations[other_user.id] = {
                'user': other_user,
                'last_message': msg,
                'unread': unread_counts.get(other_user.id, 0),
            }

    conversation_list = list(conversations.values())

    # Server-side search: filter by username or message body
    if search_query:
        q_lower = search_query.lower()
        conversation_list = [
            c for c in conversation_list
            if q_lower in c['user'].username.lower()
            or q_lower in (c['last_message'].body or '').lower()
        ]

    total_unread = sum(unread_counts.values())

    # Paginate conversations (20 per page)
    paginator = Paginator(conversation_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Exclude users already in conversations from sidebar
    conversation_user_ids = set(conversations.keys())
    following = list(
        Follow.objects.filter(follower=request.user)
        .exclude(following_id__in=conversation_user_ids)
        .select_related('following', 'following__profile')
        .order_by('-id')[:8]
    )

    return render(request, 'users/inbox.html', {
        'conversations': page_obj,
        'page_obj': page_obj,
        'total_unread': total_unread,
        'following': following,
        'search_query': search_query,
    })


@login_required
def conversation(request, username):
    """View and send messages in a conversation with a user."""
    other_user = get_object_or_404(
        User.objects.select_related('profile'),
        username=username,
    )

    if other_user == request.user:
        return redirect('users:inbox')

    msgs = Message.objects.filter(
        (Q(sender=request.user, recipient=other_user) |
         Q(sender=other_user, recipient=request.user))
    ).select_related('sender', 'sender__profile').order_by('-created_at').annotate(
        reaction_count=Count('reactions', distinct=True),
        user_reacted=Exists(MessageReaction.objects.filter(message=OuterRef('pk'), reactor=request.user))
    )[:150]  # cap at 150 most-recent messages
    # Reverse in Python so template still renders oldest→newest
    msgs = list(reversed(msgs))

    # Mark unread messages as read
    Message.objects.filter(sender=other_user, recipient=request.user, is_read=False).update(is_read=True)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if body:
            if len(body) > 2000:
                if is_ajax:
                    return JsonResponse({'ok': False, 'error': 'Message too long (max 2000 characters).'}, status=400)
                messages.error(request, 'Message is too long (max 2000 characters).')
                return redirect('users:conversation', username=username)
            msg = Message.objects.create(
                sender=request.user,
                recipient=other_user,
                body=body,
            )
            send_notification(
                recipient=other_user,
                sender=request.user,
                notification_type='message',
                text=f'{request.user.username} sent you a message',
                link=f'/users/messages/{request.user.username}/',
            )
            if is_ajax:
                return JsonResponse({'ok': True, 'id': msg.id, 'ts': int(msg.created_at.timestamp())})
            return redirect('users:conversation', username=username)

    is_following = Follow.objects.filter(follower=request.user, following=other_user).exists()
    other_user_posts = other_user.posts.filter(is_published=True).select_related('stage').order_by('-created_at')[:4]

    return render(request, 'users/conversation.html', {
        'other_user': other_user,
        'messages_list': msgs,
        'is_following': is_following,
        'other_user_posts': other_user_posts,
    })


@login_required
def notifications(request):
    """Display user notifications."""
    from collections import Counter
    notifs = list(request.user.notifications.exclude(notification_type='message').select_related('sender', 'sender__profile').order_by('-created_at')[:50])
    # Derive unread count from the fetched list — avoids a separate COUNT query
    unread_count = sum(1 for n in notifs if not n.is_read)
    sidebar_stages = Stage.objects.filter(is_active=True).only('name', 'title', 'image', 'members_count').order_by('-members_count')[:14]
    type_counts = Counter(n.notification_type for n in notifs)

    return render(request, 'users/notifications.html', {
        'notifications': notifs,
        'unread_count': unread_count,
        'stages': sidebar_stages,
        'type_counts': type_counts,
    })


@login_required
@require_POST
def mark_all_read(request):
    """AJAX: Mark all notifications as read."""
    updated = request.user.notifications.filter(is_read=False).update(is_read=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'marked': updated})
    return redirect('notifications')


@login_required
def notifications_count(request):
    """AJAX: Return unread counts + latest unread notifications for real-time display."""
    cache_key = f'notif_count_{request.user.pk}'
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    count = request.user.notifications.filter(is_read=False).exclude(notification_type='message').count()
    msg_count = Message.objects.filter(recipient=request.user, is_read=False).count()

    latest_qs = (
        request.user.notifications
        .filter(is_read=False)
        .exclude(notification_type='message')
        .select_related('sender')
        .order_by('-created_at')[:5]
    )
    latest = []
    for n in latest_qs:
        avatar_url = ''
        if n.sender:
            try:
                if n.sender.profile.avatar:
                    avatar_url = n.sender.profile.avatar.url
            except Exception:
                pass
        latest.append({
            'id': n.id,
            'type': n.notification_type,
            'text': n.text,
            'link': n.link or '',
            'sender': n.sender.username if n.sender else '',
            'sender_initial': (n.sender.username[0].upper() if n.sender else ''),
            'avatar_url': avatar_url,
        })

    data = {'count': count, 'msg_count': msg_count, 'latest': latest}
    cache.set(cache_key, data, timeout=15)
    return JsonResponse(data)


@login_required
def messages_poll(request, username):
    """AJAX: Return new messages after a given ID for real-time conversation polling."""
    other_user = get_object_or_404(
        User.objects.only('id', 'username'),
        username=username,
    )
    try:
        since_id = int(request.GET.get('since', 0))
    except (ValueError, TypeError):
        since_id = 0

    new_msgs = Message.objects.filter(
        Q(sender=request.user, recipient=other_user) |
        Q(sender=other_user, recipient=request.user),
        id__gt=since_id,
    ).only('id', 'sender_id', 'body', 'created_at').order_by('created_at')

    # Mark newly received messages as read; invalidate cached last_read if any were updated
    updated = Message.objects.filter(
        sender=other_user, recipient=request.user, id__gt=since_id, is_read=False
    ).update(is_read=True)
    if updated:
        cache.delete(f'last_read_{other_user.pk}_{request.user.pk}')

    result = []
    for m in new_msgs:
        result.append({
            'id': m.id,
            'is_mine': m.sender_id == request.user.id,
            'body': m.body,
            'ts': int(m.created_at.timestamp()),
        })

    # Is the other user currently typing?
    typing_key = f'typing_{other_user.pk}_to_{request.user.pk}'
    other_typing = bool(cache.get(typing_key))

    # Last message sent by me that has been read (cached for 2s to avoid per-poll DB hit)
    last_read_key = f'last_read_{request.user.pk}_{other_user.pk}'
    last_read = cache.get(last_read_key)
    if last_read is None:
        last_read = Message.objects.filter(
            sender=request.user, recipient=other_user, is_read=True
        ).order_by('-id').values_list('id', flat=True).first() or 0
        cache.set(last_read_key, last_read, timeout=2)

    return JsonResponse({
        'messages': result,
        'other_typing': other_typing,
        'last_read_id': last_read,
    })


@login_required
def typing_signal(request, username):
    """AJAX: Signal that the current user is typing to `username`."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    other_user = get_object_or_404(User, username=username)
    cache_key = f'typing_{request.user.pk}_to_{other_user.pk}'
    cache.set(cache_key, True, timeout=4)  # expires in 4s — no stop signal needed
    return JsonResponse({'ok': True})


@login_required
def inbox_poll(request):
    """AJAX: Return latest inbox conversations for real-time inbox updates."""
    from datetime import datetime as _dt

    PALETTE = [
        ('hsl(210,55%,38%)', 'hsl(210,55%,50%)'), ('hsl(340,50%,40%)', 'hsl(340,50%,52%)'),
        ('hsl(260,45%,42%)', 'hsl(260,45%,55%)'), ('hsl(25,60%,40%)',  'hsl(25,60%,52%)'),
        ('hsl(170,50%,32%)', 'hsl(170,50%,44%)'), ('hsl(45,55%,38%)',  'hsl(45,55%,50%)'),
        ('hsl(0,50%,42%)',   'hsl(0,50%,54%)'),   ('hsl(290,40%,40%)', 'hsl(290,40%,52%)'),
        ('hsl(150,50%,35%)', 'hsl(150,50%,47%)'), ('hsl(190,55%,38%)', 'hsl(190,55%,50%)'),
        ('hsl(220,55%,42%)', 'hsl(220,55%,54%)'), ('hsl(15,60%,38%)',  'hsl(15,60%,50%)'),
        ('hsl(315,45%,40%)', 'hsl(315,45%,52%)'), ('hsl(120,42%,34%)', 'hsl(120,42%,46%)'),
        ('hsl(55,55%,36%)',  'hsl(55,55%,48%)'),  ('hsl(200,60%,36%)', 'hsl(200,60%,48%)'),
    ]

    def _avatar_style(username):
        h = 0
        for c in str(username):
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        p = PALETTE[h % len(PALETTE)]
        return f'linear-gradient(135deg, {p[0]}, {p[1]})'

    def _time_label(value):
        if not value:
            return ''
        now = _dt.now(value.tzinfo)
        delta = now - value
        s = int(delta.total_seconds())
        if s < 60:
            return 'just now'
        if s < 3600:
            return f'{s // 60}m ago'
        if s < 86400:
            return f'{s // 3600}h ago'
        if delta.days < 365:
            return value.strftime('%b %-d')
        return value.strftime('%b %-d, %Y')

    # Rebuild conversations (same logic as inbox view but lightweight)
    msg_filter = Q(sender=request.user) | Q(recipient=request.user)
    all_messages = Message.objects.filter(msg_filter).select_related(
        'sender', 'sender__profile', 'recipient', 'recipient__profile'
    ).order_by('-created_at')[:200]

    unread_counts = dict(
        Message.objects.filter(recipient=request.user, is_read=False)
        .values('sender')
        .annotate(count=Count('id'))
        .values_list('sender', 'count')
    )

    seen = {}
    result = []
    for msg in all_messages:
        other = msg.recipient if msg.sender == request.user else msg.sender
        if other.id in seen:
            continue
        seen[other.id] = True
        avatar_url = ''
        try:
            if other.profile.avatar:
                avatar_url = other.profile.avatar.url
        except Exception:
            pass
        result.append({
            'username':        other.username,
            'avatar_url':      avatar_url,
            'avatar_style':    _avatar_style(other.username),
            'initial':         other.username[0].upper() if other.username else '?',
            'last_msg_id':     msg.id,
            'preview':         (msg.body or '')[:70],
            'last_msg_is_mine': msg.sender_id == request.user.id,
            'unread':          unread_counts.get(other.id, 0),
            'time_label':      _time_label(msg.created_at),
        })
        if len(result) >= 30:
            break

    return JsonResponse({'conversations': result})


@login_required
def change_password(request):
    """Change user password."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('users:edit_profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'users/change_password.html', {'form': form})


@login_required
@require_POST
def react_message(request, message_id):
    """Toggle ❤️ reaction on a direct message."""
    msg = get_object_or_404(Message, pk=message_id)
    if request.user not in (msg.sender, msg.recipient):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    deleted_count, _ = MessageReaction.objects.filter(message=msg, reactor=request.user).delete()
    if deleted_count:
        reacted = False
    else:
        MessageReaction.objects.create(message=msg, reactor=request.user)
        reacted = True
    return JsonResponse({'reacted': reacted, 'count': msg.reactions.count()})
