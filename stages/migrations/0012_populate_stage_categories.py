from django.db import migrations

# Stages that are not 'general' (all others default to 'general' via field default)
ENTERTAINMENT_STAGES = {'entertainment', 'football'}
TECH_STAGES = {'tech'}


def populate_categories(apps, schema_editor):
    Stage = apps.get_model('stages', 'Stage')
    Stage.objects.filter(name__in=ENTERTAINMENT_STAGES).update(category='entertainment')
    Stage.objects.filter(name__in=TECH_STAGES).update(category='tech')


def reverse_categories(apps, schema_editor):
    Stage = apps.get_model('stages', 'Stage')
    Stage.objects.all().update(category='general')


class Migration(migrations.Migration):

    dependencies = [
        ('stages', '0011_stage_category'),
    ]

    operations = [
        migrations.RunPython(populate_categories, reverse_categories),
    ]
