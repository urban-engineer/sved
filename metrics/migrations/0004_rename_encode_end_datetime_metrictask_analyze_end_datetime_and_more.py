# Generated by Django 4.1.4 on 2023-03-14 00:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0003_pooledmsssim_one_percent_min_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='metrictask',
            old_name='encode_end_datetime',
            new_name='analyze_end_datetime',
        ),
        migrations.RenameField(
            model_name='metrictask',
            old_name='encode_start_datetime',
            new_name='analyze_start_datetime',
        ),
    ]
