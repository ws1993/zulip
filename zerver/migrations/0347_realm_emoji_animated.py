# Generated by Django 3.2.6 on 2021-09-11 16:51

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0346_create_realm_user_default_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="realmemoji",
            name="is_animated",
            field=models.BooleanField(default=False),
        ),
    ]
