# Generated by Django 3.1 on 2024-12-01 11:14

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0003_reveiwrating'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ReveiwRating',
            new_name='ReviewRating',
        ),
    ]
