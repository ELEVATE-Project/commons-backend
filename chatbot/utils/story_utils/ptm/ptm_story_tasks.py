import traceback
import logging
from chatbot.models import StoryStatusChoices, Story, StoryTranslation
from chatbot.utils.story_llama_utils import translate_field

logger = logging.getLogger('django')


def save_ptm_story(
        response_json_story, language, voice_provider, profile, session, combined_reason, flow=None,
        company_bot=None
):
    try:
        name = response_json_story.get("name", "")
        district = response_json_story.get("district", "")
        school = response_json_story.get("school", "")
        role = response_json_story.get("role", "")
        ptm_experience_summary = response_json_story.get("ptm_experience_summary", "")
        key_highlights = response_json_story.get("key_highlights", "")
        perceived_changes_or_impact = response_json_story.get("perceived_changes_or_impact", "")

        other_params = {
            "user_name": name,
            "district": district,
            "school": school,
            "role": role,
            "ptm_experience_summary": ptm_experience_summary,
            "key_highlights": key_highlights,
            "perceived_changes_or_impact": perceived_changes_or_impact,
            "flow": flow,
        }

        english_title = f"{name}'s PTM Reflection" if name and name != '' else "PTM Reflection"

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = english_title
            story.language = 'en'  # Always English
            story.stage = StoryStatusChoices.COMPLETED
            story.other_params = other_params
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=english_title,
                author=profile,
                session=session,
                language='en',  # Always English
                stage=StoryStatusChoices.COMPLETED,
                other_params=other_params,
                validation_logs=combined_reason
            )
        story.save()

        if language != 'en':
            create_ptm_translation(
                story=story,
                language=language,
                english_title=english_title,
                voice_provider=voice_provider,
                company_bot=company_bot,
                ptm_data={
                    'ptm_experience_summary': ptm_experience_summary,
                    'key_highlights': key_highlights,
                    'perceived_changes_or_impact': perceived_changes_or_impact,
                    'name': name,
                    'district': district,
                    'school': school,
                    'role': role
                }
            )

        return story, ptm_experience_summary
    except Exception as e:
        logger.error("Error in save_ptm_story: %s", e, exc_info=True)
        traceback.print_exc()
        raise Exception("Failed to save PTM story")


def create_ptm_translation(story, language, english_title, voice_provider, company_bot, ptm_data):
    """Create translation for PTM story"""
    try:
        # Note: In the original code, PTM translation was commented out
        # You can uncomment and modify this based on your needs

        translated_title = translate_field(
            voice_provider=voice_provider, message_body=english_title, target_language=language
        )

        # Uncomment if you want to translate PTM fields:
        # translated_other_params = {}
        # for field in ['ptm_experience_summary', 'key_highlights', 'perceived_changes_or_impact']:
        #     if ptm_data.get(field):
        #         translated_other_params[field] = translate_field(
        #             voice_provider=voice_provider,
        #             message_body=ptm_data[field],
        #             target_language=language
        #         )

        # Create or update translation
        translation, created = StoryTranslation.objects.get_or_create(
            story=story,
            language=language,
            defaults={
                'title': translated_title,
                'content': '',
                # 'translated_other_params': translated_other_params  # Uncomment if needed
            }
        )

        if not created:
            translation.title = translated_title
            # translation.translated_other_params = translated_other_params  # Uncomment if needed
            translation.save()

        return translation

    except Exception as e:
        logger.error(f'Error creating PTM translation: %s', e, exc_info=True)
        return None
