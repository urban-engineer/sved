# Generated by Django 4.1.4 on 2023-01-14 04:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('encodes', '0002_alter_encodetask_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='encodetask',
            name='encode_framerate',
            field=models.DecimalField(decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name='encodetask',
            name='encode_type',
            field=models.CharField(max_length=3, null=True),
        ),
        migrations.AlterField(
            model_name='encodetask',
            name='encode_value',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='encodetask',
            name='progress',
            field=models.DecimalField(decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name='encodetask',
            name='seconds_remaining',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='encodetask',
            name='worker',
            field=models.CharField(max_length=128, null=True),
        ),
    ]
