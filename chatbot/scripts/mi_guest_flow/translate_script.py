from chatbot.models import Story, Voice, VoiceType, CompanyBot, ChatSession, ChatStatus
from django.db import transaction
import json
from django.db.models import Q
from chatbot.utils.audio_provider_utils import text_translate_provider
from django.utils.timezone import make_aware
from datetime import datetime
import json
from django.db import transaction
from json_repair import repair_json

from chatbot.utils.transliterate_utils import transliterate_text


###Steps To Follow:
    #First step is to call get_story_count() for given bots (Adjust the date as needed)
    #Second step is to call translate_specific_story_ids() and pass the story_ids we collected in First Step to
    #translate stories and save english version


def translate_field(voice_provider, message_body, target_language, source_language="en"):
    if not message_body or message_body == '':
        return message_body
    response = text_translate_provider(
        voice_provider=voice_provider, message_body=message_body, target_language=target_language,
        source_language=source_language
    )
    if response.get('status') == 200:
        return response.get('content')
    else:
        return message_body

def transliterate_field(voice_provider, message_body, target_language, source_language="en", is_sentence=False):
    if not message_body or message_body == '':
        return message_body
    response = transliterate_text(
        voice_provider=voice_provider, message_body=message_body, target_language=target_language,
        source_language=source_language, is_sentence=is_sentence
    )
    if response.get('status') == 200:
        return response.get('content')
    else:
        return message_body

def process_story(story):
    try:
        other_params = story.other_params or {}

        if 'english_json' in other_params:
            return f"Story ID {story.id} already translated."

        company_bot = CompanyBot.objects.get(route='/guest-story')
        voice_provider = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.TextToText
        ).first()
        voice_provider_transliterate = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.Transliterate
        ).first()

        if not voice_provider:
            return f"No voice provider for Story ID {story.id} with language {story.language}"

        raw_data = {
            "title": story.title or "",
            "content": story.content or "",
            "blurb": story.blurb or "",
            "tweet": story.tweet or "",
            "objective": story.objective or "",
            "action_steps": story.action_steps or "",
            "impact": story.impact or "",
            "micro_improvement": story.micro_improvement or "",
            "user_name": other_params.get("user_name", ""),
            "designation": other_params.get("designation", ""),
            "organization": other_params.get("organization", "")
        }

        translated_data = {}

        for key, value in raw_data.items():
            if key == "action_steps":
                translated_data[key] = translate_action_steps(
                    raw_value=value, voice_provider=voice_provider, source_language=story.language
                )
            elif key in ["user_name", "organization"]:
                word_count = len(value.strip().split())
                is_sentence = word_count > 1
                translated_data[key] = transliterate_field(
                    voice_provider=voice_provider_transliterate,  message_body=value,
                    target_language='en', source_language=story.language, is_sentence=is_sentence
                ) if value else ""
            else:
                if voice_provider_transliterate and value:
                    translated_data[key] = translate_field(
                        voice_provider=voice_provider, message_body=value, target_language='en',
                        source_language=story.language
                    )
                else:
                    translated_data[key] = value

        other_params["english_json"] = translated_data

        with transaction.atomic():
            story.other_params = other_params
            story.save(update_fields=["other_params"])

        return f"✅ Translated & updated Story ID {story.id}"

    except Exception as e:
        return f"❌ Error processing Story ID {story.id}: {str(e)}"


def translate_action_steps(raw_value, voice_provider, source_language):
    """
    Handles action_steps: can be string or list.
    """
    if not raw_value:
        return []

    # Try to parse JSON array
    parsed = None

    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except:
            try:
                parsed = json.loads(repair_json(raw_value))
            except:
                parsed = None

    if isinstance(parsed, list):
        # Confirm all elements are strings
        translated_steps = []
        for step in parsed:
            translated = translate_field(voice_provider, step, 'en', source_language) if step else ""
            translated_steps.append(translated)
        return translated_steps

    elif isinstance(raw_value, list):
        # Already a Python list
        translated_steps = []
        for step in raw_value:
            translated = translate_field(voice_provider, step, 'en', source_language) if step else ""
            translated_steps.append(translated)
        return translated_steps

    elif isinstance(raw_value, str):
        # Fallback: translate as one big string
        return translate_field(voice_provider, raw_value, 'en', source_language)

    else:
        # Unknown format
        return raw_value


def get_story_count():
    start_time = make_aware(datetime(2025, 6, 1, 0, 0))
    end_time = make_aware(datetime(2025, 7, 10, 23, 59, 59))
    bots = CompanyBot.objects.filter(route__in=["/oneshot_guest", "/guided_guest"])

    session_ids = list(
        ChatSession.objects.filter(
            created_at__gt=start_time,
            created_at__lt=end_time,
            company_bot__in=bots,
            session_status=ChatStatus.COMPLETED
        )
        .order_by('created_at')
        .values_list('session', flat=True)
    )
    print("session ids: ", session_ids)
    if session_ids:
        print("First session id: ", session_ids[0])
        print("Last session id: ", session_ids[-1])
    else:
        print("No sessions found.")

    story_ids = list(
        Story.objects.filter(session__in=session_ids)
        .exclude(Q(other_params=None) | Q(language='en'))
        .order_by('-id')
        .values_list('id', flat=True)
    )

    print(f"Total stories: {len(story_ids)}")
    return story_ids


def translate_specific_story_ids(story_ids):
    stories = Story.objects.filter(id__in=story_ids)

    print(f"Translating specific stories: {story_ids}... Total: {stories.count()}")

    for story in stories:
        print(process_story(story))