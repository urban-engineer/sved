# Generated by Django 3.2.7 on 2021-09-21 22:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0009_file_eta'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='description',
            field=models.TextField(blank=True),
        ),
    ]
