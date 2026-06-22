# Generated manually for adding theme metadata to Global Tag

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0081_alter_chatsession_session_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='is_theme',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tag',
            name='icon',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ]
