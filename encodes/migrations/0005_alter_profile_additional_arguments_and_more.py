# Generated by Django 4.1.4 on 2023-01-17 00:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('encodes', '0004_profile_additional_arguments_alter_encodetask_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='additional_arguments',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='encoder_tune',
            field=models.TextField(null=True),
        ),
    ]
