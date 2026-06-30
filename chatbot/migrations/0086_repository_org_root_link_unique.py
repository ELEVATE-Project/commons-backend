from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0085_alter_mediaorgmapping_org_id'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='repository',
            constraint=models.UniqueConstraint(
                fields=('org_id', 'root_link'),
                name='repositories_org_id_root_link_uniq',
            ),
        ),
    ]
