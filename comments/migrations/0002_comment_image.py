from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='comment_media/',
                help_text='One image or GIF per comment (max 5 MB).'
            ),
        ),
    ]
