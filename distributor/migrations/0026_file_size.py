# Generated by Django 4.1.4 on 2023-01-15 04:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0025_alter_file_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='size',
            field=models.IntegerField(null=True),
        ),
    ]