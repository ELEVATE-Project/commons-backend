from chatbot.models import Story, Voice, VoiceType, CompanyBot, ChatSession, ChatType
from django.db import transaction
import json
from django.db.models import Q
from chatbot.utils.audio_provider_utils import text_translate_provider
from django.utils.timezone import make_aware
from datetime import datetime
import logging

logger = logging.getLogger('django')

###Steps To Follow:
    #First step is to call get_story_count() (Adjust the date as needed)
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


def process_story(story):
    try:
        other_params = story.other_params or {}

        # if 'english_json' in other_params:
        #     return f"Story ID {story.id} already translated."

        raw_challenges = other_params.get('challenges_faced', [])
        raw_solutions = other_params.get('solutions_discussed', [])
        raw_user_name = other_params.get('user_name', '')
        raw_user_location = other_params.get('location', '')
        raw_organization = other_params.get('organization', '')
        raw_title = story.title or ''

        if isinstance(raw_challenges, str):
            try:
                raw_challenges = json.loads(raw_challenges)
            except:
                raw_challenges = []

        if isinstance(raw_solutions, str):
            try:
                raw_solutions = json.loads(raw_solutions)
            except:
                raw_solutions = []

        company_bot = CompanyBot.objects.get(route='/chaupal-story')
        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText
        ).first()

        if not voice_provider:
            return f"No voice provider for Story ID {story.id} with language {story.language}"

        translated_data = {
            'title': translate_field(voice_provider, raw_title, 'en', story.language),
            'challenges_faced': [translate_field(voice_provider, c, 'en', story.language) for c in raw_challenges],
            'solutions_discussed': [translate_field(voice_provider, s, 'en', story.language) for s in raw_solutions],
            'user_name': translate_field(voice_provider, raw_user_name, 'en', story.language) if raw_user_name else '',
            'organization': translate_field(voice_provider, raw_organization, 'en', story.language) if raw_organization else '',
            'location': translate_field(voice_provider, raw_user_location, 'en', story.language) if raw_user_location else '',
            'participants_count': other_params.get('participants_count', ''),
            'discussion_date': other_params.get('discussion_date', ''),
            'flow': other_params.get('flow', None),
        }

        other_params['english_json'] = translated_data

        with transaction.atomic():
            story.other_params = other_params
            story.save(update_fields=['other_params'])

        return f"✅ Translated and updated Story ID {story.id}"

    except Exception as e:
        return f"❌ Error in Story ID {story.id}: {str(e)}"


def translate_stories_to_english(start=0, end=100):
    session_ids = list(
        ChatSession.objects.filter(session_type=ChatType.shikshaChaupal)
        .values_list('session', flat=True)
    )

    stories = Story.objects.filter(session__in=session_ids) \
                  .exclude(Q(other_params=None) | Q(language='en')) \
                  .order_by('-id')[start:end]

    logger.info(f"Translating stories from {start} to {end}... Total: {stories.count()}")
    print(f"Translating stories from {start} to {end}... Total: {stories.count()}")

    for story in stories:
        print(process_story(story))


def get_translate_story_count(start_time, end_time):
    if not start_time:
        start_time = make_aware(datetime(2025, 7, 15, 0, 0))
    if not end_time:
        end_time = make_aware(datetime(2025, 7, 28, 23, 59, 59))

    session_ids = list(
        ChatSession.objects.filter(
            session_type=ChatType.shikshaChaupal,
            created_at__gt=start_time,
            created_at__lt=end_time
        )
        .order_by('created_at')
        .values_list('session', flat=True)
    )
    if session_ids:
        logger.info(f"Found {len(session_ids)} sessions")
        logger.info(f"First session ID: {session_ids[0]}, Last session ID: {session_ids[-1]}")

        print("First session id: ", session_ids[0])
        print("Last session id: ", session_ids[-1])
    else:
        logger.info(f"No sessions found.")
        print("No sessions found.")

    story_ids = list(
        Story.objects.filter(session__in=session_ids)
        .exclude(Q(other_params=None) | Q(language='en'))
        .order_by('-id')
        .values_list('id', flat=True)
    )

    logger.info(f"Total stories: {len(story_ids)}")
    print(f"Total stories: {len(story_ids)}")
    return story_ids


def translate_specific_story_ids(story_ids):
    stories = Story.objects.filter(id__in=story_ids)
    logger.info(f"Translating specific stories: {story_ids}... Total: {stories.count()}")
    print(f"Translating specific stories: {story_ids}... Total: {stories.count()}")

    for story in stories:
        print(process_story(story))