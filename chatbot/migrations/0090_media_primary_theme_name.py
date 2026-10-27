from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0089_resource_themes'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalmedia',
            name='primary_theme_name',
            field=models.CharField(blank=True, editable=False, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='media',
            name='primary_theme_name',
            field=models.CharField(blank=True, editable=False, max_length=255, null=True),
        ),
    ]
