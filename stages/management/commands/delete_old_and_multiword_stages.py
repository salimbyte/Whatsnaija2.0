from django.core.management.base import BaseCommand
from stages.models import Stage
from django.utils import timezone
import re

class Command(BaseCommand):
    help = 'Delete stages with more than one word in name or not created within the last 7 days.'

    def handle(self, *args, **options):
        now = timezone.now()
        week_ago = now - timezone.timedelta(days=7)
        # Stages with more than one word in name
        multiword = Stage.objects.filter(name__regex=r'\\s')
        # Stages not created within the last week
        old = Stage.objects.exclude(created_at__gte=week_ago)
        # Union of both querysets
        to_delete = multiword | old
        count = to_delete.distinct().count()
        to_delete.distinct().delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} stages (multi-word name or not created this week).'))
