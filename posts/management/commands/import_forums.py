import random
import re
import time
import textwrap
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from comments.models import Comment, CommentDislike, CommentLike, CommentReaction
from posts.models import DisLike, Like, Post
from stages.models import Stage


NAIRALAND_BASE = "https://nairaland.com"
LINDA_DEFAULT = "https://lindaikejisblog.com"
LINDA_FALLBACK = "https://www.lindaikejisblog.com"

DEFAULT_BOARDS = "politics,entertainment"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

HEADER_RE = re.compile(
    r"^(Re:\s+)?(?P<title>.+?)\s+by\s+(?P<user>[^:]+):\s+"
    r"(?P<time>\d{1,2}:\d{2}\s*[ap]m)\s+On\s+(?P<date>[A-Za-z]{3}\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)

VIEW_RE = re.compile(r"\(([\d,]+)\s+Views\)", re.IGNORECASE)
LIKES_RE = re.compile(r"\b(\d+)\s+Likes?\b", re.IGNORECASE)
LIKE_THIS_RE = re.compile(r"Like this!\s*(\d+)", re.IGNORECASE)
DISLIKE_THIS_RE = re.compile(r"Dislike this!\s*(\d+)", re.IGNORECASE)
ABOUT_AGO_RE = re.compile(r"about\s+(\d+)\s+(years?|months?|days?)\s+ago", re.IGNORECASE)


class Command(BaseCommand):
    help = (
        "Scrape Nairaland + Linda Ikeja Blog and import posts, users, and comments. "
        "Use responsibly and only with permission."
    )

    def add_arguments(self, parser):
        parser.add_argument("--wipe", action="store_true", help="Delete prior imported posts from these sources.")
        parser.add_argument("--force", action="store_true", help="Required with --wipe to confirm destructive delete.")
        parser.add_argument("--nairaland-boards", default=DEFAULT_BOARDS, help="Comma-separated boards.")
        parser.add_argument("--nairaland-pages", type=int, default=5, help="Pages per board to scan initially.")
        parser.add_argument("--linda-pages", type=int, default=5, help="Number of Linda Ikeja pages to scan.")
        parser.add_argument("--min-lines", type=int, default=20, help="Minimum body lines (wrapped at 80 cols).")
        parser.add_argument("--min-comments", type=int, default=10, help="Minimum comments per post.")
        parser.add_argument("--target-nairaland", type=int, default=30, help="Target total posts from Nairaland.")
        parser.add_argument("--target-linda", type=int, default=20, help="Target total posts from Linda Ikeja.")
        parser.add_argument("--max-pages", type=int, default=25, help="Hard cap on pages per source.")
        parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds).")
        parser.add_argument("--user-agent", type=str, default=DEFAULT_UA, help="User-Agent header.")
        parser.add_argument("--nairaland-base", type=str, default=NAIRALAND_BASE, help="Base URL for Nairaland.")
        parser.add_argument("--linda-base", type=str, default=LINDA_DEFAULT, help="Base URL for Linda Ikeja.")
        parser.add_argument("--linda-fallback", type=str, default=LINDA_FALLBACK, help="Fallback URL for Linda Ikeja.")
        parser.add_argument("--ignore-robots", action="store_true", help="Ignore robots.txt (not recommended).")
        parser.add_argument("--no-sim-reactions", action="store_true", help="Disable simulated likes/dislikes.")

    def handle(self, *args, **options):
        if options["wipe"] and not options["force"]:
            self.stdout.write(self.style.ERROR("Refusing to wipe without --force."))
            return

        self.user_agent = options["user_agent"]
        self.delay = max(0.0, options["delay"])
        self.min_lines = max(1, options["min_lines"])
        self.min_comments = max(0, options["min_comments"])
        self.ignore_robots = options["ignore_robots"]
        self.sim_reactions = not options["no_sim_reactions"]

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )
        self.robots = {}
        self.nairaland_base = options["nairaland_base"].rstrip("/")
        self.nairaland_alt = self._toggle_www(self.nairaland_base)
        self.linda_base = options["linda_base"].rstrip("/")
        self.linda_fallback = options["linda_fallback"].rstrip("/")
        self.linda_alt = self._toggle_www(self.linda_base)

        if options["wipe"]:
            self._wipe_imported()
            self.stdout.write(self.style.SUCCESS("Wiped prior imported posts from Nairaland/Linda Ikeja."))

        User = get_user_model()
        self.user_cache = {}
        self.raw_user_cache = {}
        self.all_users = []

        boards = [b.strip().lower() for b in options["nairaland_boards"].split(",") if b.strip()]
        nairaland_posts = self._import_nairaland(
            boards=boards,
            pages=options["nairaland_pages"],
            target=options["target_nairaland"],
            max_pages=options["max_pages"],
            User=User,
        )
        self.stdout.write(self.style.SUCCESS(f"Nairaland imported posts: {len(nairaland_posts)}"))

        linda_posts = self._import_linda(
            base_url=self.linda_base,
            fallback_url=self.linda_fallback,
            pages=options["linda_pages"],
            target=options["target_linda"],
            max_pages=options["max_pages"],
            User=User,
        )
        self.stdout.write(self.style.SUCCESS(f"Linda Ikeja imported posts: {len(linda_posts)}"))

        self.stdout.write(self.style.SUCCESS("Import completed."))

    def _wipe_imported(self):
        Post.objects.filter(url__icontains="nairaland.com").delete()
        Post.objects.filter(url__icontains="lindaikeja").delete()

    def _fetch(self, url):
        if not self.ignore_robots and not self._can_fetch(url):
            self.stdout.write(self.style.WARNING(f"Robots disallows: {url}"))
            return ""
        try:
            resp = self.session.get(url, timeout=15, allow_redirects=True)
            if resp.status_code == 403:
                alt = self._alt_url(url)
                if alt and alt != url:
                    resp = self.session.get(alt, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            time.sleep(self.delay)
            return resp.text
        except Exception as exc:
            alt = self._alt_url(url)
            if alt and alt != url:
                try:
                    resp = self.session.get(alt, timeout=15, allow_redirects=True)
                    resp.raise_for_status()
                    time.sleep(self.delay)
                    return resp.text
                except Exception:
                    pass
            self.stdout.write(self.style.WARNING(f"Fetch failed: {url} ({exc})"))
            return ""

    def _can_fetch(self, url):
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self.robots.get(base)
        if rp is None:
            rp = RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                rp = None
            self.robots[base] = rp
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def _import_nairaland(self, boards, pages, target, max_pages, User):
        stage_map = {}
        posts_created = []

        for board in boards:
            stage = self._get_or_create_stage(
                name=f"nl_{board}"[:20],
                title=f"Nairaland {board.title()}",
                category=self._map_category(board),
            )
            stage_map[board] = stage

        for board in boards:
            page_urls = self._nairaland_board_pages(board, pages, max_pages)
            thread_urls = []
            for page_url in page_urls:
                html = self._fetch(page_url)
                if not html:
                    continue
                thread_urls.extend(self._extract_nairaland_thread_urls(html))
                if len(thread_urls) >= target:
                    break

            thread_urls = self._dedupe(thread_urls)
            for thread_url in thread_urls:
                if len(posts_created) >= target:
                    break
                html = self._fetch(thread_url)
                if not html:
                    continue
                parsed = self._parse_nairaland_thread(html)
                if not parsed:
                    continue
                title, op, replies, view_count = parsed
                if self._line_count(op["body"]) < self.min_lines:
                    continue
                if len(replies) < self.min_comments:
                    continue

                post = self._create_post(
                    title=title,
                    body=op["body_html"],
                    author=op["user"],
                    stage=stage_map.get(board),
                    source_url=thread_url,
                    created_at=op["created_at"],
                    view_count=view_count,
                )
                if not post:
                    continue

                comment_users = []
                for reply in replies:
                    comment = self._create_comment(
                        post=post,
                        user=reply["user"],
                        body=reply["body"],
                        created_at=reply["created_at"],
                    )
                    if comment:
                        comment_users.append(reply["user"])
                        if self.sim_reactions:
                            self._apply_reactions_to_comment(comment, reply.get("likes", 0))

                if self.sim_reactions:
                    self._apply_reactions_to_post(post, op.get("likes", 0), comment_users)

                posts_created.append(post)

        return posts_created

    def _import_linda(self, base_url, fallback_url, pages, target, max_pages, User):
        posts_created = []
        stage = self._get_or_create_stage(
            name="lindaikeja",
            title="Linda Ikeja Blog",
            category="entertainment",
        )

        base_html = self._fetch(base_url)
        if not base_html and fallback_url:
            base_url = fallback_url
            base_html = self._fetch(base_url)
        if not base_html:
            return posts_created

        page_urls = self._discover_linda_pages(base_url, base_html, pages, max_pages)
        post_urls = []
        for page_url in page_urls:
            html = self._fetch(page_url)
            if not html:
                continue
            post_urls.extend(self._extract_linda_post_urls(html, base_url))
            if len(post_urls) >= target * 2:
                break

        post_urls = self._dedupe(post_urls)
        for post_url in post_urls:
            if len(posts_created) >= target:
                break
            html = self._fetch(post_url)
            if not html:
                continue
            parsed = self._parse_linda_post(html)
            if not parsed:
                continue
            title, body_html, body_text, comments = parsed
            if self._line_count(body_text) < self.min_lines:
                continue
            if len(comments) < self.min_comments:
                continue

            author = self._get_or_create_user("lindaikeja")
            post = self._create_post(
                title=title,
                body=body_html,
                author=author,
                stage=stage,
                source_url=post_url,
                created_at=None,
                view_count=0,
            )
            if not post:
                continue

            comment_users = []
            for item in comments:
                user = self._get_or_create_user(item["user"])
                comment = self._create_comment(
                    post=post,
                    user=user,
                    body=item["body"],
                    created_at=item.get("created_at"),
                )
                if comment:
                    comment_users.append(user)
                    if self.sim_reactions:
                        self._apply_reactions_to_comment(comment, item.get("likes", 0), item.get("dislikes", 0))

            if self.sim_reactions:
                self._apply_reactions_to_post(post, 0, comment_users)

            posts_created.append(post)

        return posts_created

    def _nairaland_board_pages(self, board, pages, max_pages):
        pages = min(max_pages, max(1, pages))
        base = f"{self.nairaland_base}/{board}"
        urls = [base]
        for page in range(2, pages + 1):
            urls.append(f"{base}/{page}")
        return urls

    def _extract_nairaland_thread_urls(self, html):
        soup = BeautifulSoup(html, "html.parser")
        urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#"):
                continue
            if href.startswith("http"):
                parsed = urlparse(href)
                if "nairaland.com" not in parsed.netloc:
                    continue
                path = parsed.path
            else:
                path = href
            match = re.match(r"^/(\d+)(/[^/]+)?$", path)
            if not match:
                continue
            thread_id = int(match.group(1))
            if thread_id < 1000:
                continue
            urls.add(urljoin(self.nairaland_base + "/", path.lstrip("/")))
        return list(urls)

    def _parse_nairaland_thread(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else "Nairaland Thread"
        title = title.replace(" - Nairaland", "").strip()

        text = soup.get_text("\n")
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]

        view_count = 0
        for ln in lines:
            m = VIEW_RE.search(ln)
            if m:
                view_count = int(m.group(1).replace(",", ""))
                break

        posts = []
        current = None
        for ln in lines:
            m = HEADER_RE.match(ln)
            if m:
                if current:
                    posts.append(current)
                current = {
                    "user_raw": m.group("user").strip(),
                    "created_at": self._parse_nairaland_dt(m.group("time"), m.group("date")),
                    "body_lines": [],
                }
                continue
            if not current:
                continue
            if self._is_noise_line(ln):
                continue
            current["body_lines"].append(ln)

        if current:
            posts.append(current)

        if not posts:
            return None

        normalized_posts = []
        for item in posts:
            body_text = self._clean_body(item["body_lines"])
            likes = self._extract_likes(item["body_lines"])
            user = self._get_or_create_user(item["user_raw"])
            normalized_posts.append(
                {
                    "user": user,
                    "created_at": item["created_at"],
                    "body": body_text,
                    "body_html": self._to_html(body_text),
                    "likes": likes,
                }
            )

        op = normalized_posts[0]
        replies = normalized_posts[1:]
        return title, op, replies, view_count

    def _discover_linda_pages(self, base_url, first_html, pages, max_pages):
        urls = [base_url]
        next_url = base_url
        html = first_html
        for _ in range(1, min(pages, max_pages)):
            soup = BeautifulSoup(html, "html.parser")
            older = soup.find("a", string=re.compile("Older", re.IGNORECASE))
            if not older or not older.get("href"):
                break
            next_url = urljoin(base_url, older["href"])
            if next_url in urls:
                break
            urls.append(next_url)
            html = self._fetch(next_url)
            if not html:
                break
        return urls

    def _extract_linda_post_urls(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#"):
                continue
            full = urljoin(base_url, href)
            if "lindaikeja" not in urlparse(full).netloc:
                continue
            if not re.search(r"/20\d{2}/", full):
                continue
            urls.add(full.split("#")[0])
        return list(urls)

    def _parse_linda_post(self, html):
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("h1") or soup.find("h2", class_=re.compile("post-title", re.I))
        title = title_tag.get_text(strip=True) if title_tag else "Linda Ikeja Blog Post"

        body_node = (
            soup.find("div", class_=re.compile("post-body|entry-content|article-body|post-content", re.I))
            or soup.find("article")
        )
        if not body_node:
            return None

        paragraphs = [p.get_text(" ", strip=True) for p in body_node.find_all("p")]
        if not paragraphs:
            raw = body_node.get_text("\n", strip=True)
            paragraphs = [ln for ln in raw.splitlines() if ln.strip()]

        body_text = "\n".join(paragraphs)
        body_html = self._to_html(body_text)

        comments = self._parse_linda_comments(soup)
        return title, body_html, body_text, comments

    def _parse_linda_comments(self, soup):
        comments = []
        container = soup.find(id=re.compile("comment", re.I)) or soup.find("div", class_=re.compile("comment", re.I))
        if container:
            for block in container.find_all(["div", "li"], class_=re.compile("comment", re.I)):
                parsed = self._parse_comment_block(block.get_text("\n"))
                if parsed:
                    comments.append(parsed)

        if comments:
            return comments

        text = soup.get_text("\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        in_comments = False
        current = None
        for ln in lines:
            if ln.lower().startswith("comments"):
                in_comments = True
                continue
            if not in_comments:
                continue
            if ln.lower().startswith("post a comment"):
                break
            if ABOUT_AGO_RE.search(ln):
                if current:
                    comments.append(current)
                name = ln.split("about")[0].strip()
                current = {"user": name or "anonymous", "body_lines": [], "likes": 0, "dislikes": 0}
                continue
            if current:
                like_m = LIKE_THIS_RE.search(ln)
                dislike_m = DISLIKE_THIS_RE.search(ln)
                if like_m:
                    current["likes"] = int(like_m.group(1))
                    continue
                if dislike_m:
                    current["dislikes"] = int(dislike_m.group(1))
                    continue
                if ln.lower().startswith("like this") or ln.lower().startswith("reply"):
                    continue
                current["body_lines"].append(ln)

        if current:
            comments.append(current)

        normalized = []
        for item in comments:
            body = self._clean_body(item.get("body_lines", []))
            normalized.append(
                {
                    "user": item.get("user") or "anonymous",
                    "body": body,
                    "likes": item.get("likes", 0),
                    "dislikes": item.get("dislikes", 0),
                }
            )
        return normalized

    def _parse_comment_block(self, text):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return None
        user = lines[0]
        body_lines = []
        likes = 0
        dislikes = 0
        for ln in lines[1:]:
            like_m = LIKE_THIS_RE.search(ln)
            dislike_m = DISLIKE_THIS_RE.search(ln)
            if like_m:
                likes = int(like_m.group(1))
                continue
            if dislike_m:
                dislikes = int(dislike_m.group(1))
                continue
            if ABOUT_AGO_RE.search(ln):
                continue
            if ln.lower().startswith("reply"):
                continue
            body_lines.append(ln)
        body = self._clean_body(body_lines)
        if not body:
            return None
        return {"user": user, "body": body, "likes": likes, "dislikes": dislikes}

    def _parse_nairaland_dt(self, time_str, date_str):
        cleaned = f"{time_str}".replace(" ", "").upper()
        try:
            dt = datetime.strptime(f"{cleaned} {date_str}", "%I:%M%p %b %d, %Y")
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except Exception:
            return timezone.now()

    def _line_count(self, text):
        if not text:
            return 0
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) >= self.min_lines:
            return len(lines)
        return len(textwrap.wrap(text, width=80))

    def _clean_body(self, lines):
        cleaned = [ln for ln in lines if ln and not self._is_noise_line(ln)]
        body = "\n".join(cleaned).strip()
        return body

    def _to_html(self, text):
        if not text:
            return ""
        paras = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not paras:
            return ""
        return "<p>" + "</p><p>".join(paras) + "</p>"

    def _is_noise_line(self, ln):
        noise = {
            "share",
            "print",
            "report",
            "quote",
            "like",
            "reply",
            "nairaland forum",
            "create new topic",
            "register",
            "login",
            "trending",
            "recent",
            "search",
        }
        lower = ln.strip().lower()
        if lower in noise:
            return True
        if lower.startswith("you are currently not a logged in member"):
            return True
        if lower.startswith("se" ) and "sections" in lower:
            return True
        return False

    def _extract_likes(self, lines):
        for ln in reversed(lines):
            m = LIKES_RE.search(ln)
            if m:
                return int(m.group(1))
        return 0

    def _get_or_create_user(self, raw_name):
        raw_name = (raw_name or "").strip()
        if raw_name in self.raw_user_cache:
            return self.raw_user_cache[raw_name]

        base = re.sub(r"\(.*?\)", "", raw_name).strip() or "anonymous"
        base = base.replace(" ", "_")
        base = re.sub(r"[^A-Za-z0-9_]", "", base)[:30] or "anonymous"
        username = base.lower()

        User = get_user_model()
        if username in self.user_cache:
            user = self.user_cache[username]
        else:
            user = User.objects.filter(username=username).first()
            if not user:
                user = User(username=username, email=f"{username}@import.local")
                user.set_unusable_password()
                user.save()
            self.user_cache[username] = user
            if user not in self.all_users:
                self.all_users.append(user)

        self.raw_user_cache[raw_name] = user
        return user

    def _get_or_create_stage(self, name, title, category):
        stage, _ = Stage.objects.get_or_create(
            name=name,
            defaults={"title": title, "category": category, "is_active": True},
        )
        return stage

    def _map_category(self, board):
        board = board.lower()
        if board in {"sports", "sport"}:
            return "sports"
        if board in {"entertainment", "music", "movies", "celebs"}:
            return "entertainment"
        if board in {"tech", "science", "programming"}:
            return "tech"
        return "general"

    def _create_post(self, title, body, author, stage, source_url, created_at, view_count):
        if Post.objects.filter(url=source_url).exists():
            return None
        post = Post(
            title=title[:240],
            body=body,
            author=author,
            stage=stage,
            url=source_url,
            is_published=True,
            view_count=view_count or 0,
        )
        post.save()
        if created_at:
            Post.objects.filter(pk=post.pk).update(created_at=created_at, updated_at=created_at)
        if stage and author:
            stage.members.add(author)
            stage.members_count = stage.members.count()
            stage.save(update_fields=["members_count"])
        return post

    def _create_comment(self, post, user, body, created_at):
        if not body:
            return None
        comment = Comment.objects.create(post=post, user=user, body=body, is_anon=False)
        if created_at:
            Comment.objects.filter(pk=comment.pk).update(created_at=created_at, updated_at=created_at)
        return comment

    def _apply_reactions_to_post(self, post, like_count, comment_users):
        pool = list({u for u in comment_users if u})
        if not pool:
            return
        random.shuffle(pool)
        like_count = min(like_count or random.randint(3, min(12, len(pool))), len(pool))
        dislike_count = min(random.randint(1, max(1, like_count // 3)), len(pool))
        for user in pool[:like_count]:
            Like.objects.get_or_create(user=user, post=post)
        for user in pool[-dislike_count:]:
            if user:
                DisLike.objects.get_or_create(user=user, post=post)

    def _apply_reactions_to_comment(self, comment, like_count=0, dislike_count=0):
        pool = list(self.all_users)
        if not pool:
            return
        random.shuffle(pool)
        like_count = min(like_count or random.randint(1, min(6, len(pool))), len(pool))
        dislike_count = min(dislike_count or random.randint(0, min(3, len(pool))), len(pool))
        for user in pool[:like_count]:
            CommentLike.objects.get_or_create(user=user, comment=comment)
        for user in pool[-dislike_count:]:
            CommentDislike.objects.get_or_create(user=user, comment=comment)
        for user in pool[: min(3, len(pool))]:
            CommentReaction.objects.get_or_create(comment=comment, user=user, emoji=random.choice(["🔥", "💯", "😂", "🤔"]))

    def _dedupe(self, urls):
        seen = set()
        out = []
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def _toggle_www(self, base):
        parsed = urlparse(base)
        host = parsed.netloc
        if host.startswith("www."):
            host = host[4:]
        else:
            host = f"www.{host}"
        return parsed._replace(netloc=host).geturl()

    def _alt_url(self, url):
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if "nairaland.com" in host:
            alt_base = self.nairaland_alt
        elif "lindaikeja" in host:
            alt_base = self.linda_alt
        else:
            return ""
        return urljoin(alt_base + "/", parsed.path.lstrip("/")) + (f"?{parsed.query}" if parsed.query else "")
