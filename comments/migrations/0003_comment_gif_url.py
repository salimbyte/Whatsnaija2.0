from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comments', '0002_comment_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='gif_url',
            field=models.URLField(blank=True, default='', help_text='Tenor GIF URL (used when a GIF is picked instead of uploaded).'),
        ),
    ]
