from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0027_reserved_username'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ban_until',
            field=models.DateTimeField(blank=True, null=True, db_index=True),
        ),
    ]
