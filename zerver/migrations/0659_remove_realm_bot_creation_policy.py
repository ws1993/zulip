# Generated by Django 5.0.10 on 2025-01-27 11:24

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0658_alter_realm_can_create_bots_group_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="realm",
            name="bot_creation_policy",
        ),
    ]
