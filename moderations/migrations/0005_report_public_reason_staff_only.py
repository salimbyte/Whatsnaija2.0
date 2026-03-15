from django.db import migrations, models


def migrate_reviewed(apps, schema_editor):
    Report = apps.get_model('moderations', 'Report')
    Report.objects.filter(status='reviewed').update(status='dismissed')


class Migration(migrations.Migration):

    dependencies = [
        ('moderations', '0004_add_performance_indexes_2'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='public_reason',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='report',
            name='staff_only',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(migrate_reviewed, migrations.RunPython.noop),
    ]
