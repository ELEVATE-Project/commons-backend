from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add AI_SERVICE to LLMProvider.choices and reword the provider help text.

    State-only: choices and help_text are not database-level attributes, so this
    emits no DDL. It exists so the model state Django replays matches the model,
    and so the change is reviewable and reversible — the earlier migration that
    introduced this field has been applied everywhere and must not be edited.
    """

    dependencies = [
        ('chatbot', '0087_add_source_provider_to_media'),
    ]

    operations = [
        migrations.AlterField(
            model_name='companybot',
            name='provider',
            field=models.CharField(choices=[('bedrock', 'BEDROCK'), ('bedrock/converse', 'BEDROCK_CONVERSE'), ('openai', 'OPENAI'), ('ai_service', 'AI_SERVICE')], default='bedrock/converse', help_text='How commons calls the model. BEDROCK, BEDROCK_CONVERSE and OPENAI call the provider directly; AI_SERVICE routes through the AI Service gateway, which owns the vendor and model choice (AI_SERVICE_PROVIDER / AI_SERVICE_MODEL).', max_length=100),
        ),
        migrations.AlterField(
            model_name='historicalcompanybot',
            name='provider',
            field=models.CharField(choices=[('bedrock', 'BEDROCK'), ('bedrock/converse', 'BEDROCK_CONVERSE'), ('openai', 'OPENAI'), ('ai_service', 'AI_SERVICE')], default='bedrock/converse', help_text='How commons calls the model. BEDROCK, BEDROCK_CONVERSE and OPENAI call the provider directly; AI_SERVICE routes through the AI Service gateway, which owns the vendor and model choice (AI_SERVICE_PROVIDER / AI_SERVICE_MODEL).', max_length=100),
        ),
    ]
