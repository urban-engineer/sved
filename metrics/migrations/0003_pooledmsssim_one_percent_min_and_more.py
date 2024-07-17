# Generated by Django 4.1.4 on 2023-03-11 01:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0002_alter_metrictask_options_alter_pooledmsssim_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pooledmsssim',
            name='one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=7),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pooledmsssim',
            name='point_one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=7),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pooledpsnr',
            name='one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=8),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pooledpsnr',
            name='point_one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=8),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pooledvmaf',
            name='one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=9),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pooledvmaf',
            name='point_one_percent_min',
            field=models.DecimalField(decimal_places=6, default=-1, max_digits=9),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='metrictask',
            name='neg_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='metrictask',
            name='status',
            field=models.IntegerField(choices=[(0, 'Created'), (1, 'Queued'), (2, 'Downloading'), (3, 'In Progress'), (4, 'Uploading'), (5, 'Complete')], default=0),
        ),
    ]
