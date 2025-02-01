# Generated by Django 1.11.6 on 2017-11-30 00:13
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0001_initial"),
        ("confirmation", "0004_remove_confirmationmanager"),
    ]

    operations = [
        migrations.AddField(
            model_name="confirmation",
            name="realm",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to="zerver.Realm"
            ),
        ),
    ]
