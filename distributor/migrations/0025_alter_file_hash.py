# Generated by Django 4.1.4 on 2023-01-14 04:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0024_file_hash'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='hash',
            field=models.CharField(max_length=40, null=True),
        ),
    ]