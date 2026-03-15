from django.db import migrations, models


def seed_reserved(apps, schema_editor):
    ReservedUsername = apps.get_model('users', 'ReservedUsername')
    defaults = [
        'admin', 'administrator', 'support', 'help', 'security', 'root', 'system',
        'staff', 'moderator', 'mod', 'official', 'api', 'terms', 'rules', 'privacy',
        'contact', 'about', 'team', 'billing', 'payments',
        'whatsnaija', 'whatsnaijaofficial', 'whatsnaijasupport',
    ]
    for name in defaults:
        name = name.strip()
        if not name:
            continue
        ReservedUsername.objects.get_or_create(
            name=name,
            defaults={
                'name_lower': name.lower(),
                'reason': 'default reserved',
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0026_remove_userprofile_onboarding_interests'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReservedUsername',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('name_lower', models.CharField(db_index=True, editable=False, max_length=150, unique=True)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Reserved Username',
                'verbose_name_plural': 'Reserved Usernames',
                'ordering': ['name_lower'],
            },
        ),
        migrations.RunPython(seed_reserved, migrations.RunPython.noop),
    ]
