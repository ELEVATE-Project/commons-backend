from django.conf import settings
from django.core.cache import cache
from django.db import migrations, transaction


OLD_CODE = 'Teaching_Learning_Practises'
NEW_CODE = 'Teaching_Learning_Practices'
OLD_NAME = 'Teaching and Learning Practises'
NEW_NAME = 'Teaching and Learning Practices'


def clear_theme_cache():
    if settings.REDIS_CACHE_ENABLED:
        cache.delete_many([
            'resource_themes:list:v1',
            'resource_themes:primary:list:v1',
            'resource_themes:list:v1:published',
            'resource_themes:primary:list:v1:published',
        ])


def rename_theme(apps, schema_editor, old_code, new_code, old_name, new_name):
    database = schema_editor.connection.alias
    # Deferred foreign keys allow the code and its media links to change
    # together in this atomic migration, preserving the theme ID.
    themes = apps.get_model('chatbot', 'ResourceTheme').objects.using(database).filter(
        code=old_code,
    )
    themes.filter(name=old_name).update(name=new_name)
    themes.update(code=new_code)
    for model_name in ('Media', 'HistoricalMedia'):
        # primary_theme_id is the ORM attribute for the primary_theme_code
        # database column. Update every matching code, regardless of its label.
        media = apps.get_model('chatbot', model_name).objects.using(database).filter(
            primary_theme_id=old_code,
        )
        media.filter(primary_theme_name=old_name).update(primary_theme_name=new_name)
        media.update(primary_theme_id=new_code)
    transaction.on_commit(clear_theme_cache, using=database)


def forwards(apps, schema_editor):
    rename_theme(apps, schema_editor, OLD_CODE, NEW_CODE, OLD_NAME, NEW_NAME)


def backwards(apps, schema_editor):
    rename_theme(apps, schema_editor, NEW_CODE, OLD_CODE, NEW_NAME, OLD_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0091_remove_resourcetheme_media_count'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
