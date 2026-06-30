from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0084_mediaorgmapping'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mediaorgmapping',
            name='org_id',
            field=models.TextField(),
        ),
    ]
