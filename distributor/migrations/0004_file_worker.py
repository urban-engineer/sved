# Generated by Django 3.2.7 on 2021-09-05 21:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0003_file_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='worker',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]