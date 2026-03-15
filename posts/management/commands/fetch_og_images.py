"""
Backfill og_image for existing link posts that don't have one yet.

Usage:
    python manage.py fetch_og_images              # process all un-scraped link posts
    python manage.py fetch_og_images --limit 50   # cap at 50 posts (useful for testing)
    python manage.py fetch_og_images --force       # re-scrape even posts that already have og_image set
"""

from django.core.management.base import BaseCommand
from posts.models import Post
from posts.og_scraper import fetch_og_image


class Command(BaseCommand):
    help = "Fetch og:image for link posts that have a URL but no OG image stored"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Max posts to process (0 = all)")
        parser.add_argument("--force", action="store_true", help="Re-scrape even posts that already have an og_image")

    def handle(self, *args, **options):
        qs = Post.objects.filter(is_published=True, url__gt="")
        if not options["force"]:
            qs = qs.filter(og_image="")

        if options["limit"]:
            qs = qs[:options["limit"]]

        total = qs.count() if hasattr(qs, 'count') else len(qs)
        self.stdout.write(f"Processing {total} post(s)…")

        found = 0
        for post in qs:
            img_url = fetch_og_image(post.url)
            if img_url:
                Post.objects.filter(pk=post.pk).update(og_image=img_url)
                found += 1
                self.stdout.write(f"  ✓  {post.title[:60]}")
            else:
                self.stdout.write(self.style.WARNING(f"  –  {post.title[:60]} (no image found)"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. {found}/{total} posts got an OG image."))
