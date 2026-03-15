from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker
import random

from posts.models import Post
from stages.models import Stage
from users.models import User

class Command(BaseCommand):
    help = 'Seed the database with random posts.'

    def add_arguments(self, parser):
        parser.add_argument('--number', type=int, default=50, help='Number of posts to create')

    def handle(self, *args, **options):
        fake = Faker()
        number = options['number']
        users = list(User.objects.all())
        stages = list(Stage.objects.all())

        if not users or not stages:
            self.stdout.write(self.style.ERROR('You need at least one user and one stage to seed posts.'))
            return

        created = 0
        for _ in range(number):
            user = random.choice(users)
            stage = random.choice(stages)
            post = Post(
                title=fake.sentence(nb_words=8),
                body=fake.paragraph(nb_sentences=5),
                author=user,
                stage=stage,
                is_published=True,
                created_at=timezone.now(),
            )
            post.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f'Successfully created {created} posts.'))
