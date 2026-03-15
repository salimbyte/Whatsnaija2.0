"""
OG image scraper for Vaze.

Workflow:
  When a post with a URL is saved, fetch_og_image_async() fires a daemon
  thread that scrapes the page and stores the og:image URL in Post.og_image.
  The feed reads Post.og_image at display time — zero scraping cost per visit.

Safety:
  - 5-second page fetch timeout, reads at most 512 KB of HTML
  - Never raises: any failure leaves Post.og_image unchanged (stays '')
  - Thread is a daemon so it can't block server shutdown
"""

import logging
import re
import threading
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PAGE_TIMEOUT   = 5
_MAX_PAGE_BYTES = 512_000

# Domains we deliberately skip — streaming paywalls, download tools, and sites
# known to block scrapers or return useless/misleading OG images.
_BLOCKED_DOMAINS = {
    # Streaming / paywall
    'pazu.app', 'pazu.io', 'netflix.com', 'hulu.com', 'disneyplus.com',
    'primevideo.com', 'max.com', 'peacocktv.com', 'paramountplus.com',
    'spotify.com', 'tidal.com', 'deezer.com', 'applemusic.com',
    # Short video / social (no useful OG for forum context)
    'youtube.com', 'youtu.be', 'tiktok.com', 'reels.instagram.com',
    # Download / piracy tools
    'z-lib.org', 'zlibrary.org', 'libgen.rs',
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VazeBot/1.0; +https://vaze.ng)",
    "Accept": "text/html,application/xhtml+xml",
}


def _is_valid_image_url(url: str) -> bool:
    return bool(url) and urlsplit(url).scheme in ("http", "https")


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is on the scraper blacklist."""
    host = urlsplit(url).hostname or ''
    host = host.removeprefix('www.')
    return any(host == d or host.endswith('.' + d) for d in _BLOCKED_DOMAINS)


def fetch_og_image(url: str) -> str:
    """
    Synchronously scrape *url* and return the absolute og:image URL, or ''.
    Used by the backfill management command.
    """
    if not url:
        return ''
    if _is_blocked(url):
        logger.debug("OG scrape skipped (blacklisted domain): %s", url)
        return ''
    try:
        resp = requests.get(
            url, headers=_HEADERS, timeout=_PAGE_TIMEOUT,
            stream=True, allow_redirects=True,
        )
        resp.raise_for_status()

        if "html" not in resp.headers.get("Content-Type", ""):
            return ''

        raw = b""
        for chunk in resp.iter_content(chunk_size=8192):
            raw += chunk
            if len(raw) >= _MAX_PAGE_BYTES:
                break

        soup = BeautifulSoup(raw, "html.parser")
        candidates = []

        for attr in ("og:image", "og:image:url"):
            tag = soup.find("meta", property=attr)
            if tag and tag.get("content"):
                candidates.append(tag["content"].strip())

        if not candidates:
            tag = soup.find("meta", attrs={"name": re.compile(r"twitter:image", re.I)})
            if tag and tag.get("content"):
                candidates.append(tag["content"].strip())

        if not candidates:
            tag = soup.find("link", rel="image_src")
            if tag and tag.get("href"):
                candidates.append(tag["href"].strip())

        for candidate in candidates:
            absolute = urljoin(resp.url, candidate)
            if _is_valid_image_url(absolute):
                return absolute

        return ''

    except Exception as exc:
        logger.debug("OG scrape failed for %s: %s", url, exc)
        return ''


def fetch_og_image_async(post_id: int, url: str) -> None:
    """
    Fire-and-forget: scrapes *url* in a background thread and writes the
    result to Post.og_image. Called immediately after post.save().
    """
    def _run():
        from posts.models import Post  # local import avoids Django app-registry issues in threads
        image_url = fetch_og_image(url)
        if image_url:
            Post.objects.filter(pk=post_id).update(og_image=image_url)
            logger.debug("OG image saved for post %s: %s", post_id, image_url)

    t = threading.Thread(target=_run, daemon=True, name=f"og-scrape-{post_id}")
    t.start()
