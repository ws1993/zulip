# Generated by Django 1.11.2 on 2017-07-16 08:57
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0090_userprofile_high_contrast_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="realm",
            name="allow_edit_history",
            field=models.BooleanField(default=True),
        ),
    ]
