from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0090_media_primary_theme_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='resourcetheme',
            name='media_count',
        ),
    ]
