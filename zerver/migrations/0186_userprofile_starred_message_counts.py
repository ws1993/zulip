# Generated by Django 1.11.14 on 2018-08-17 06:06

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0185_realm_plan_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="starred_message_counts",
            field=models.BooleanField(default=False),
        ),
    ]
