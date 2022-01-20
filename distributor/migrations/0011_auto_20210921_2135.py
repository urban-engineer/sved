# Generated by Django 3.2.7 on 2021-09-22 01:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0010_profile_description'),
    ]

    operations = [
        migrations.RenameField(
            model_name='file',
            old_name='completion_datetime',
            new_name='encode_end_datetime',
        ),
        migrations.AddField(
            model_name='file',
            name='encode_start_datetime',
            field=models.DateTimeField(default='1970-01-01 00:00:00Z'),
        ),
    ]