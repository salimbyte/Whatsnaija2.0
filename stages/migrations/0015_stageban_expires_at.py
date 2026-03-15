from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stages', '0014_seed_new_stages'),
    ]

    operations = [
        migrations.AddField(
            model_name='stageban',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
