from django.db import migrations


NEW_STAGES = [
    # Entertainment
    ('music',        'Music & Radio',        'entertainment'),
    ('movies',       'TV & Movies',          'entertainment'),
    ('celebrities',  'Celebrities',          'entertainment'),
    ('comedy',       'Comedy & Jokes',       'entertainment'),
    ('fashion',      'Fashion',              'entertainment'),
    # Sports
    ('sports',       'Sports',               'sports'),
    ('gaming',       'Gaming',               'sports'),
    # Technology
    ('programming',  'Programming',          'tech'),
    ('crypto',       'Crypto & Web3',        'tech'),
    # Creative
    ('photography',  'Photography',          'creative'),
    ('art',          'Art & Design',         'creative'),
    ('literature',   'Literature & Books',   'creative'),
    ('diy',          'DIY',                  'creative'),
    # Interests
    ('fitness',      'Fitness',              'interests'),
    ('outdoors',     'Outdoors & Nature',    'interests'),
    ('diaspora',     'Diaspora',             'interests'),
]


def seed_and_reassign(apps, schema_editor):
    Stage = apps.get_model('stages', 'Stage')
    # Reassign football and existing entertainment stage
    Stage.objects.filter(name='football').update(category='sports')
    # Seed new stages
    for name, title, category in NEW_STAGES:
        Stage.objects.get_or_create(
            name=name,
            defaults={'title': title, 'category': category, 'is_active': True},
        )


def reverse_seed(apps, schema_editor):
    Stage = apps.get_model('stages', 'Stage')
    Stage.objects.filter(name='football').update(category='entertainment')
    names = [s[0] for s in NEW_STAGES]
    Stage.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stages', '0013_expand_categories'),
    ]

    operations = [
        migrations.RunPython(seed_and_reassign, reverse_seed),
    ]
