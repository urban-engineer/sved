# Generated by Django 4.1.4 on 2023-03-16 03:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0028_rename_path_file_directory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='hash',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
    ]
