# Generated by Django 1.11.14 on 2018-08-22 09:57

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("zerver", "0187_userprofile_is_billing_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="enable_login_emails",
            field=models.BooleanField(default=True),
        ),
    ]
