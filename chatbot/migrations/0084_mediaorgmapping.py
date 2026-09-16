from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0083_repository'),
    ]

    operations = [
        migrations.CreateModel(
            name='MediaOrgMapping',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('media_id', models.ForeignKey(db_column='media_id', on_delete=django.db.models.deletion.CASCADE, related_name='media_org_mappings', to='chatbot.media')),
                ('org_id', models.BigIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
