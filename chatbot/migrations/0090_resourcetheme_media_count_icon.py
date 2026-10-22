from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chatbot', '0089_resource_themes'),
    ]

    operations = [
        migrations.AddField(
            model_name='resourcetheme',
            name='media_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='resourcetheme',
            name='icon',
            field=models.CharField(blank=True, default=None, max_length=1000, null=True),
        ),
    ]
