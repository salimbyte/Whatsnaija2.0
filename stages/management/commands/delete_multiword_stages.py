from django.core.management.base import BaseCommand
from stages.models import Stage
import re

class Command(BaseCommand):
    help = 'Delete all stages whose name contains more than one word.'

    def handle(self, *args, **options):
        multiword_stages = Stage.objects.filter(name__regex=r'\\s')
        count = multiword_stages.count()
        multiword_stages.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} stages with more than one word in their name.'))
