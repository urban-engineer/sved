# Generated by Django 3.2.7 on 2021-09-23 19:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('distributor', '0011_auto_20210921_2135'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='duration',
            field=models.DecimalField(decimal_places=3, default=0.0, max_digits=9),
            preserve_default=False,
        ),
    ]
