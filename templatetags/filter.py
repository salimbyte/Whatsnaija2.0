import re
import html as _html_module
import bleach
from datetime import datetime
from urllib.parse import urlsplit

from django import template
from django.forms.boundfield import BoundField

register = template.Library()

# Add 'add_class' filter for form fields
@register.filter(name='add_class')
def add_class(field, css):
    if isinstance(field, BoundField):
        return field.as_widget(attrs={**field.field.widget.attrs, 'class': css})
    return field


@register.filter(name='avatar_color')
def avatar_color(username):
    """Return a CSS gradient based on username hash for letter avatars."""
    palette = [
        ('hsl(210,55%,38%)', 'hsl(210,55%,50%)'),   # blue
        ('hsl(340,50%,40%)', 'hsl(340,50%,52%)'),    # rose
        ('hsl(260,45%,42%)', 'hsl(260,45%,55%)'),    # purple
        ('hsl(25,60%,40%)',  'hsl(25,60%,52%)'),     # orange
        ('hsl(170,50%,32%)', 'hsl(170,50%,44%)'),    # teal
        ('hsl(45,55%,38%)',  'hsl(45,55%,50%)'),     # amber
        ('hsl(0,50%,42%)',   'hsl(0,50%,54%)'),      # red
        ('hsl(290,40%,40%)', 'hsl(290,40%,52%)'),    # violet
        ('hsl(150,50%,35%)', 'hsl(150,50%,47%)'),    # emerald
        ('hsl(190,55%,38%)', 'hsl(190,55%,50%)'),    # cyan
        ('hsl(220,55%,42%)', 'hsl(220,55%,54%)'),    # indigo
        ('hsl(15,60%,38%)',  'hsl(15,60%,50%)'),     # burnt orange
        ('hsl(315,45%,40%)', 'hsl(315,45%,52%)'),    # pink
        ('hsl(120,42%,34%)', 'hsl(120,42%,46%)'),    # forest green
        ('hsl(55,55%,36%)',  'hsl(55,55%,48%)'),     # gold
        ('hsl(200,60%,36%)', 'hsl(200,60%,48%)'),    # sky blue
    ]
    # Hash by full name for distinct colours across similar names
    hash_val = 0
    for char in str(username):
        hash_val = (hash_val * 31 + ord(char)) & 0xFFFFFFFF
    idx = hash_val % len(palette)
    return f'linear-gradient(135deg, {palette[idx][0]}, {palette[idx][1]})'


@register.filter(name='avatar_initials')
def avatar_initials(name):
    """Return 2-letter initials: first letter uppercase + second letter lowercase."""
    name_str = str(name).strip()
    if len(name_str) >= 2:
        return name_str[0].upper() + name_str[1].lower()
    elif name_str:
        return name_str[0].upper()
    return '?'


# Compiled YouTube URL pattern.
yt_link = re.compile(
    r'(https?://)?(www\.)?((youtu\.be/)|(youtube\.com/watch/?\?v=))([A-Za-z0-9-_]+)(\S*)',
    re.I,
)
yt_embed = (
    '<div class="youtube">'
    ' <iframe style="max-width: 100%, max-height: 100%"'
    ' width="460" height="215"'
    ' src="https://www.youtube.com/embed/{0}"'
    ' frameborder="0"'
    ' allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"'
    ' allowfullscreen></iframe>'
    ' </div>'
)

@register.filter(name='convert_ytframe')
def convert_ytframe(text):
    def replace(match):
        youtube_id = match.groups()[5]
        return yt_embed.format(youtube_id)

    return yt_link.sub(replace, text)


@register.filter(name='convert_links_except_src')
def convert_links_except_src(text):
    """Wrap bare URLs in anchor tags. Only http/https URLs are linked to prevent XSS."""
    # Match only http/https URLs so javascript: and other schemes are never wrapped.
    link_pattern = re.compile(r'\bhttps?://\S+\b')

    for match in link_pattern.findall(text):
        if f'src="{match}"' not in text and f'href="{match}"' not in text:
            processed_link = f'<a href="{match}" rel="noopener noreferrer">{match}</a>'
            text = text.replace(match, processed_link)

    return text


@register.filter(name='safe_for_tags')
def safe_for_tags(value):

    ALLOWED_TAGS = ['br', 'em', 'strong', 'u', 'iframe', 'a', 'img']
    ALLOWED_ATTRS = {
        'a':   ['href', 'rel'],
        'img': ['src', 'alt', 'style'],
    }

    cleaned_user_input = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
    return cleaned_user_input


@register.filter(name='safe_post_body')
def safe_post_body(value):
    """Sanitize post body HTML — allows rich CKEditor formatting, strips scripts and inline styles."""
    ALLOWED_TAGS = [
        'p', 'br', 'b', 'i', 'em', 'strong', 'u', 's', 'strike',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'blockquote', 'pre', 'code',
        'a', 'img', 'iframe',
        'table', 'thead', 'tbody', 'tr', 'td', 'th',
        'figure', 'figcaption', 'div', 'span',
    ]
    ALLOWED_ATTRS = {
        'a': ['href', 'title', 'rel', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'iframe': ['src', 'width', 'height', 'allowfullscreen', 'frameborder', 'allow', 'title'],
        'td': ['colspan', 'rowspan'],
        'th': ['colspan', 'rowspan'],
    }
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)




@register.filter(name='get_domain_from_url')
def get_domain_from_url(url):
    parsed_url = urlsplit(url)
    domain = parsed_url.netloc
    return domain


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Allow dict[key] lookups in templates: {{ my_dict|get_item:key }}"""
    return dictionary.get(key)


@register.filter(name='clean_excerpt')
def clean_excerpt(value, arg=20):
    """
    Strip HTML tags, unescape entities, and return a clean N-word excerpt.
    Picks the FIRST paragraph that contains >= 15 words so that short sponsor
    blurbs or single-sentence intros are skipped in favour of real content.
    Falls back to the longest paragraph if none reaches the threshold.
    """
    if not value:
        return ''
    word_count = int(arg)

    def _plain(html_frag):
        text = re.sub(r'<[^>]+>', ' ', html_frag)
        text = _html_module.unescape(text)
        text = text.replace('\xa0', ' ')
        return re.sub(r'\s+', ' ', text).strip()

    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', value, re.IGNORECASE | re.DOTALL)
    if paragraphs:
        texts = [_plain(p) for p in paragraphs]
        # First paragraph with enough real words
        best = next((t for t in texts if len(t.split()) >= 15), None)
        if best is None:
            best = max(texts, key=lambda t: len(t.split())) if texts else ''
    else:
        best = _plain(value)

    words = best.split()
    if len(words) > word_count:
        return ' '.join(words[:word_count]) + '…'
    return best



@register.filter(name='custom_timesince')
def custom_timesince(value, default=None):
    if not value:
        return default

    now = datetime.now(value.tzinfo)
    delta = now - value

    # Calculate years, days, and hours
    years = delta.days // 365
    days = delta.days % 365
    hours = delta.seconds // 3600

    if years > 0:
        return f"{years}y ago"
    elif days > 0:
        return f"{days}d ago"
    elif hours > 0:
        return f"{hours}h ago"
    else:
        return "just now"

@register.filter(name='inbox_time')
def inbox_time(value):
    """Smart inbox timestamp: 'Xm ago' / 'Xh ago' (< 24h), 'Mon D' (< 1yr), 'D Mon YYYY' (older)."""
    if not value:
        return ''
    now = datetime.now(value.tzinfo)
    delta = now - value
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return 'just now'
    if total_seconds < 3600:
        m = total_seconds // 60
        return f'{m}m ago'
    if total_seconds < 86400:
        h = total_seconds // 3600
        return f'{h}h ago'
    if delta.days < 365:
        return value.strftime('%b %-d')
    return value.strftime('%b %-d, %Y')


@register.filter(name='strip_sender')
def strip_sender(text, sender_username):
    """Strip the sender username prefix from notification text."""
    if sender_username and text.startswith(sender_username + ' '):
        return text[len(sender_username) + 1:]
    return text

