import json
from chatbot.models import StoryTranslation, Voice, VoiceType
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.story_utils.format_utils import get_formatted_story
from chatbot.utils.story_utils.story_utils import get_story_company_bot


def extract_update_data(request):
    """Extract and organize update data from request"""
    return {
        'other_params': request.data.get('other_params', {}),
        'formatted_content': request.data.get('formatted_content'),
        'session': request.data.get('session'),
        'access_token': request.data.get('access_token'),
        'flow': request.data.get('flow')
    }


def get_or_create_translation(story, language, update_data):
    """Get existing translation or create new one"""
    translation, created = StoryTranslation.objects.get_or_create(
        story=story,
        language=language,
        defaults={
            'title': story.title,
            'content': story.content or '',
            'other_params': update_data['other_params'].copy()
        }
    )
    return translation


def update_translation_fields(translation, update_data, language):
    """Update translation fields with new data"""
    if update_data.get('other_params'):
        translation.other_params = update_data['other_params'].copy()

    if update_data.get('formatted_content'):
        process_formatted_content(
            translation, update_data['formatted_content'],
        )

    translation.save()


def process_formatted_content(translation, formatted_content):
    """Process formatted content and extract/translate text - SIMPLIFIED VERSION"""
    translation.formatted_content = formatted_content

    try:
        if isinstance(formatted_content, str):
            formatted_data = json.loads(formatted_content)
        else:
            formatted_data = formatted_content

        content_parts = []

        for item in formatted_data:
            if item.get('type') == 'paragraph' and item.get('data', {}).get('text'):
                content_parts.append(item['data']['text'])

        if content_parts:
            translation.content = '\n'.join(content_parts)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error processing formatted_content: {e}")


def sync_to_main_story(story, translation, update_data, source_language):
    """Sync translation changes back to main story (English)"""
    flow = update_data.get('flow')
    voice_provider = get_voice_provider('en', flow)
    if not voice_provider:
        print("Could not find voice provider")
        return

    if update_data['other_params']:
        print("Translating other_params to English")
        english_other_params = translate_other_params(
            story.other_params or {},
            update_data['other_params'],
            voice_provider,
            source_language
        )
        story.other_params = english_other_params

    if update_data.get('formatted_content') and translation.content:
        sync_content_to_story(story, translation, voice_provider, source_language)

    story.save()


def translate_other_params(current_params, new_params, voice_provider, source_language):
    """Translate other_params fields back to English"""
    english_params = current_params.copy()

    translatable_fields = ['challenges_faced', 'solutions_discussed', 'question_answers']
    non_translatable_fields = ['participants_count', 'discussion_date', 'flow', 'location']

    for field in translatable_fields:
        if field in new_params:
            english_params[field] = translate_nested_structure(
                new_params[field], voice_provider, source_language
            )

    for field in non_translatable_fields:
        if field in new_params:
            english_params[field] = new_params[field]

    return english_params


def translate_field_value(value, voice_provider, source_language):
    """Translate a field value (handles both strings and lists)"""
    if isinstance(value, list):
        return [
            translate_field(
                voice_provider=voice_provider,
                message_body=item,
                target_language='en',
                source_language=source_language
            ) for item in value
        ]
    else:
        return translate_field(
            voice_provider=voice_provider,
            message_body=value,
            target_language='en',
            source_language=source_language
        )


def sync_content_to_story(story, translation, voice_provider, source_language):
    """Sync content and formatted_content to main story - SIMPLIFIED VERSION"""
    print("sync_content_to_story called")
    english_content = translate_field(
        voice_provider=voice_provider,
        message_body=translation.content,
        target_language='en',
        source_language=source_language
    )
    story.content = english_content

    story.formatted_content = get_formatted_story(story)


def get_voice_provider(language, flow):
    """Get voice provider for specified language"""
    print("Flow is : ", flow)
    print("language is : ", language)
    bot, validate_bot = get_story_company_bot(None, flow)
    print("bot: ", bot)
    if bot:
        print("bot route: ", bot.route)
    return Voice.objects.filter(
        company_bot=bot,
        type=VoiceType.TextToText,
        language=language
    ).first()


def translate_nested_structure(data, voice_provider, source_language):
    """
    Generic handler for translating nested data structures (dicts and lists).
    Recursively processes any combination of dicts, lists, and strings.
    """
    if isinstance(data, dict):
        return {
            key: translate_nested_structure(value, voice_provider, source_language)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [
            translate_nested_structure(item, voice_provider, source_language)
            for item in data
        ]
    elif isinstance(data, str) and data.strip():
        return translate_field(
            voice_provider=voice_provider,
            message_body=data,
            target_language='en',
            source_language=source_language
        )
    else:
        return data
