# Generated by Django 4.2.7 on 2023-11-26 03:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0030_remove_file_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='ffprobe_information',
            field=models.JSONField(null=True),
        ),
    ]