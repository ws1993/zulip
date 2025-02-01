# Generated by Django 4.2.5 on 2023-09-21 14:07

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0488_set_default_value_for_can_access_all_users_group"),
    ]

    operations = [
        migrations.AlterField(
            model_name="realm",
            name="can_access_all_users_group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="+",
                to="zerver.usergroup",
            ),
        ),
    ]
