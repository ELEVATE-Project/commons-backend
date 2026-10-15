import django.core.validators
import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models

PUBLISHED_STATUS = 'published'
MEDIA_MODELS = ('media', 'historicalmedia')

PRIMARY_THEMES = [
    {
        'code': 'Foundational_Learning',
        'name': 'Foundational Learning',
        'description': (
            "The development of core literacy and numeracy competencies, typically in the early and primary grades. "
            "Covers curriculum, pedagogy, assessment, and practice resources aimed directly at building a child's "
            "ability to read, write, and do basic mathematics — including remediation for students below grade-level.\n"
            "Includes: FLN curricula, reading/numeracy practice tools, phonics and fluency resources, FLN-focused "
            "teacher diaries or trackers."
        ),
    },
    {
        'code': 'School_Governance',
        'name': 'School Governance',
        'description': (
            "This theme is about the school as a functioning institution — who leads it, how decisions get made, "
            "how it plans and holds itself accountable, and how power and voice are distributed within it.\n"
            "Includes- school leadership and headmaster development; school-level planning, budgeting, and "
            "accountability processes; internal communication and feedback systems; timetabling and academic "
            "calendar management; school self-assessment and improvement-planning tools; student voice and "
            "participation structures within the school (councils, leadership bodies, peer-governance models); "
            "staff role clarity and delegation frameworks; grievance-redressal mechanisms at the school level."
        ),
    },
    {
        'code': 'Community_Engagement',
        'name': 'Community Engagement',
        'description': (
            "The involvement of parents, families, and the wider local community in a child's education and "
            "school life.\n\n"
            "What can fall under it: parent sensitization, communication, and capacity-building; School Management "
            "Committee and panchayat involvement; home-visit and home-learning support models; community "
            "mobilization around enrolment, attendance, or retention; local partnerships (with anganwadis, health "
            "workers, civil society); volunteer or mentor programmes drawing from the community; "
            "community-awareness campaigns on education issues."
        ),
    },
    {
        'code': 'System_Thinking',
        'name': 'System Thinking',
        'description': (
            "System Thinking is about seeing and working on the structural, root-cause layer that sits above any "
            "single school, asking why a problem exists across many schools and what's systemically driving it, "
            "rather than treating it as an isolated event. A resource belongs here if its primary value is helping "
            "someone reason about why a problem exists and how the system producing it should be redesigned — not "
            "simply because it operates at a large scale.\n\n"
            "What can fall under it: theory of change and logical framework design; needs assessments, landscape "
            "studies, and root-cause analyses; district- or state-level capacity-building (e.g. for education "
            "officials, DIETs, block/cluster resource centres); policy analysis and alignment tools; "
            "multi-stakeholder coordination frameworks; programme-level monitoring and evaluation design; resource "
            "allocation and planning models operating above the school level; frameworks for scaling or "
            "replicating interventions."
        ),
    },
    {
        'code': 'Teaching_Learning_Practises',
        'name': 'Teaching and Learning Practises',
        'description': (
            "This theme is about how teaching and learning happens inside the classroom. Everything around teacher "
            "capacity, pedagogy, and the practice of teaching and learning.\n\n"
            "What can fall under it: teacher training, coaching, and mentoring; classroom observation and feedback "
            "tools; lesson planning and teaching-learning material development; pedagogical approaches "
            "(project-based learning, activity-based learning, differentiated instruction); classroom management "
            "and culture-building; student engagement and motivation strategies within lessons; peer-learning and "
            "peer-teaching models; subject-specific teaching resources beyond foundational literacy/numeracy; "
            "teacher motivation, wellbeing, and professional identity work; career guidance and skill-readiness "
            "delivered through classroom or school programming."
        ),
    },
    {
        'code': 'Child_Rights',
        'name': 'Child Rights',
        'description': (
            "Awareness, education, and protection grounded explicitly in a child's rights.\n\n"
            "What can fall under it: child rights curricula and awareness-building; child protection and "
            "safeguarding policies and protocols; grievance and reporting mechanisms for child safety; advocacy "
            "materials framed around children's legal or constitutional rights; work addressing child labour, "
            "early marriage, corporal punishment, or other rights violations; participation rights (a child's "
            "right to be heard, distinct from governance-structure participation)."
        ),
    },
    {
        'code': 'Movement',
        'name': 'Movement',
        'description': (
            "This theme is about the sector as a collective project — the work of building an ecosystem of aligned "
            "actors (organizations, teachers, students, communities) around a shared cause, and shifting narrative "
            "or practice at a scale beyond what any single programme could achieve alone. It's the most outward- "
            "and forward-facing theme: it's less about a specific intervention and more about momentum — advocacy, "
            "coalition, storytelling, spread.\n\n"
            "What can fall under it: cross-organization collaboration and coalition-building; ambassador or "
            "champion models (teachers, students, alumni, community leaders); advocacy and public-narrative "
            "campaigns; storytelling and testimony resources used to build momentum around a cause; efforts to "
            "influence policy or public opinion at scale; volunteer or fellowship networks organized around a "
            "shared mission; events, conclaves, or convenings designed to build a field or sector."
        ),
    },
    {
        'code': 'Inclusion',
        'name': 'Inclusion',
        'description': (
            "Ensuring equitable access, participation, and belonging for children who face structural barriers to "
            "learning.\n"
            "This theme is about who gets left out of \"normal\" school design by default, and what it takes to "
            "actively include them children with disabilities, from marginalized communities, with language "
            "barriers, or who don't fit the assumed profile a mainstream intervention is built for.\n\n"
            "What can fall under it: disability-inclusive education practices and resources; gender-equity work; "
            "support for marginalized castes, tribes, religious minorities, migrant or out-of-school children; "
            "multilingual and language-access approaches; social-emotional learning and wellbeing support, "
            "anti-bullying and belonging-focused classroom practices; accessibility of infrastructure, materials, "
            "and assessment for children with diverse needs."
        ),
    },
    {
        'code': 'Miscellaneous',
        'name': 'Miscellaneous',
        'description': (
            "if any resource cannot be mapped to the list of pre-existing/pre-defined primary themes, it can be "
            "mapped to a separate theme called “Miscellaneous.” This will include all resources that do not align "
            "with any of the existing primary themes."
        ),
    },
]


def seed_primary_themes(apps, schema_editor):
    ResourceTheme = apps.get_model('chatbot', 'ResourceTheme')
    for theme in PRIMARY_THEMES:
        ResourceTheme.objects.update_or_create(
            code=theme['code'],
            defaults={
                'name': theme['name'],
                'description': theme['description'],
                'is_primary': True,
                'status': PUBLISHED_STATUS,
            },
        )


def primary_theme_field(model_name):
    if model_name == 'historicalmedia':
        return models.ForeignKey(blank=True, db_column='primary_theme_code', db_constraint=False, limit_choices_to={'is_primary': True}, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='chatbot.resourcetheme', to_field='code')
    return models.ForeignKey(blank=True, db_column='primary_theme_code', limit_choices_to={'is_primary': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='primary_media', to='chatbot.resourcetheme', to_field='code')


def media_theme_fields():
    return [
        migrations.AddField(model_name=model_name, name=field_name, field=field)
        for model_name in MEDIA_MODELS
        for field_name, field in (
            ('primary_theme', primary_theme_field(model_name)),
            ('primary_theme_confidence', models.FloatField(blank=True, null=True)),
            ('primary_theme_reasoning', models.TextField(blank=True, null=True)),
            ('needs_review', models.BooleanField(db_index=True, default=False)),
        )
    ]


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0088_alter_companybot_provider'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResourceTheme',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('code', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('is_primary', models.BooleanField(db_index=True, default=False)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published')], db_index=True, default='draft', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_themes', to='chatbot.profile')),
            ],
            options={
                'verbose_name': 'Resource Theme',
                'verbose_name_plural': 'Resource Themes',
                'db_table': 'themes',
                'ordering': ['-is_primary', 'name'],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='themes_name_ci_uniq')],
            },
        ),
        migrations.RunPython(seed_primary_themes, migrations.RunPython.noop),
        *media_theme_fields(),
        migrations.CreateModel(
            name='MediaSecondaryTheme',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('confidence', models.FloatField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ('reasoning', models.TextField(blank=True, default='')),
                ('match_type', models.CharField(blank=True, choices=[('matched', 'Matched existing theme'), ('deduplicated', 'Generated name resolved to existing theme'), ('created', 'New theme created')], db_index=True, max_length=20, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('media', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='secondary_theme_links', to='chatbot.media')),
                ('theme', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media_links', to='chatbot.resourcetheme')),
            ],
            options={
                'verbose_name': 'Media Secondary Theme',
                'verbose_name_plural': 'Media Secondary Themes',
                'db_table': 'media_secondary_themes',
                'ordering': ['-confidence'],
                'constraints': [models.UniqueConstraint(fields=('media', 'theme'), name='media_secondary_theme_uniq')],
            },
        ),
    ]
