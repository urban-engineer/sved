# Generated by Django 3.2.7 on 2021-09-04 23:19

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='path',
        ),
    ]
