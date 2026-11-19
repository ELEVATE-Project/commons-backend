from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


# Snapshot of the existing organizations, keyed by stable slug rather than ID.
# Use name-derived variants only; do not guess expansions of NEAID or CWS.
INITIAL_ALIASES = {
    'involve': ['involve'],
    'M4C': ['mantra', 'mantra for change', 'mantra 4 change'],
    'vidhyavidhai': ['vidhya vidhai', 'vidhya vidhai foundation'],
    'SEF': ['simple education', 'simple education foundation'],
    'NagaEd': ['naga ed'],
    'NEAID': ['neaid'],
    'Prajayatna': ['prajayatna'],
    'shikshalokamtest': ['shikshalokam test', 'shiksha lokam test'],
    'shikshalokamstaging': ['shikshalokam', 'shiksha lokam'],
    'SEE': ['social emotional ethical learning', 'see learning'],
    'cws': ['cws'],
    'Alokit': ['alokit', 'alokit school leadership development'],
}


def seed_aliases(apps, schema_editor):
    Company = apps.get_model('chatbot', 'Company')
    companies = Company.objects.using(schema_editor.connection.alias)
    for slug, aliases in INITIAL_ALIASES.items():
        companies.filter(slug=slug).update(alias=aliases)


class Migration(migrations.Migration):
    dependencies = [
        ('chatbot', '0092_correct_teaching_learning_theme_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='alias',
            field=ArrayField(
                base_field=models.CharField(max_length=100),
                default=list,
                blank=True,
                size=None,
            ),
        ),
        # Reversing AddField drops the aliases along with the column.
        migrations.RunPython(seed_aliases, migrations.RunPython.noop),
    ]
