from django.core.management.base import BaseCommand
from stages.models import Stage
from users.models import User
import random

class Command(BaseCommand):
    help = 'Add 200 random members to each of 10 random stages.'

    def handle(self, *args, **options):
        stages = list(Stage.objects.order_by('?')[:10])
        users = list(User.objects.all())
        if len(users) < 200:
            self.stdout.write(self.style.ERROR('Not enough users to add as members.'))
            return
        for stage in stages:
            new_members = random.sample(users, 200)
            for user in new_members:
                stage.members.add(user)
            stage.members_count = stage.members.count()
            stage.save()
            self.stdout.write(self.style.SUCCESS(f'Added 200 members to stage: {stage.name}'))
        self.stdout.write(self.style.SUCCESS('Done adding 200 members to each of 10 stages.'))
