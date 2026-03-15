from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0025_userprofile_onboarding_interests'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='onboarding_interests',
        ),
    ]
