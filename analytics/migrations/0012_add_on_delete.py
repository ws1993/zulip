# Generated by Django 1.11.6 on 2018-01-29 08:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0011_clear_analytics_tables"),
    ]

    operations = [
        migrations.AlterField(
            model_name="installationcount",
            name="anomaly",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL, to="analytics.Anomaly"
            ),
        ),
        migrations.AlterField(
            model_name="realmcount",
            name="anomaly",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL, to="analytics.Anomaly"
            ),
        ),
        migrations.AlterField(
            model_name="streamcount",
            name="anomaly",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL, to="analytics.Anomaly"
            ),
        ),
        migrations.AlterField(
            model_name="usercount",
            name="anomaly",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.SET_NULL, to="analytics.Anomaly"
            ),
        ),
    ]
