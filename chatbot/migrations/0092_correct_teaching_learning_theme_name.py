from django.conf import settings
from django.core.cache import cache
from django.db import migrations, transaction


THEME_CODE = 'Teaching_Learning_Practises'
PREVIOUSLY_CHANGED_CODE = 'Teaching_Learning_Practices'
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


def rename_theme(apps, schema_editor, old_name, new_name):
    database = schema_editor.connection.alias
    # Restore the original code if an earlier version of 0092 changed it.
    # Keep this code on rollback too; only the display-name change is reversed.
    # Deferred foreign keys allow the theme and media links to change together.
    themes = apps.get_model('chatbot', 'ResourceTheme').objects.using(database)
    themes.filter(code=PREVIOUSLY_CHANGED_CODE).update(code=THEME_CODE)
    themes.filter(
        code=THEME_CODE, name=old_name,
    ).update(name=new_name)
    for model_name in ('Media', 'HistoricalMedia'):
        media = apps.get_model('chatbot', model_name).objects.using(database)
        media.filter(primary_theme_id=PREVIOUSLY_CHANGED_CODE).update(
            primary_theme_id=THEME_CODE,
        )
        media.filter(
            primary_theme_id=THEME_CODE, primary_theme_name=old_name,
        ).update(primary_theme_name=new_name)
    transaction.on_commit(clear_theme_cache, using=database)


def forwards(apps, schema_editor):
    rename_theme(apps, schema_editor, OLD_NAME, NEW_NAME)


def backwards(apps, schema_editor):
    rename_theme(apps, schema_editor, NEW_NAME, OLD_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0091_remove_resourcetheme_media_count'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
