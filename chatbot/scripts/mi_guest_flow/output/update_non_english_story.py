import re
import logging
from datetime import datetime

from chatbot.models import (
    Story, ChatSession, SessionFlowName, Voice, VoiceType
)
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.transliterate_utils import transliterate_text, get_transliteration_output

logger = logging.getLogger("django")

OUTPUT_FILE = "guest_mi_story_fix_report.txt"

# ---------- LANGUAGE DETECTION ----------
ENGLISH_LETTER_REGEX = re.compile(r'[A-Za-z]')
ANY_LETTER_REGEX = re.compile(r'[A-Za-z\u00C0-\u024F\u0900-\u097F]')


def is_non_english_text(text):
    """Check if text contains non-English characters"""
    if not text or not isinstance(text, str):
        return False
    # Ignore numbers / dates / symbols
    if not ANY_LETTER_REGEX.search(text):
        return False
    return not ENGLISH_LETTER_REGEX.search(text)


def find_non_english_in_list(lst, field_name):
    """Check if any item in list contains non-English text"""
    found = []
    if not isinstance(lst, list):
        return found

    for i, item in enumerate(lst):
        if isinstance(item, str) and is_non_english_text(item):
            found.append(f"{field_name}[{i}]")
    return found


# ---------- MAIN SCRIPT ----------
def fix_guest_mi_story_stories():
    stories = Story.objects.filter(
        other_params__flow=SessionFlowName.GuestMiStory
    )

    total = stories.count()
    fixed = []
    failed = []
    skipped = []

    for story in stories:
        offending_fields = []

        # 🔹 CHECK MAIN STORY FIELDS
        if is_non_english_text(story.title):
            offending_fields.append("story.title")

        if is_non_english_text(story.content):
            offending_fields.append("story.content")

        if is_non_english_text(story.objective):
            offending_fields.append("story.objective")

        if is_non_english_text(story.impact):
            offending_fields.append("story.impact")

        if is_non_english_text(story.micro_improvement):
            offending_fields.append("story.micro_improvement")

        if is_non_english_text(story.tweet):
            offending_fields.append("story.tweet")

        if is_non_english_text(story.blurb):
            offending_fields.append("story.blurb")

        if is_non_english_text(story.location):
            offending_fields.append("story.location")

        # Check action_steps (can be string or list)
        if isinstance(story.action_steps, str):
            if is_non_english_text(story.action_steps):
                offending_fields.append("story.action_steps")
        elif isinstance(story.action_steps, list):
            offending_fields.extend(find_non_english_in_list(story.action_steps, "story.action_steps"))

        # 🔹 CHECK OTHER_PARAMS FIELDS
        if story.other_params:
            # Check personal info fields that should be transliterated
            for field in ["user_name", "location", "organization", "designation"]:
                val = story.other_params.get(field)
                if val and is_non_english_text(val):
                    offending_fields.append(f"other_params.{field}")

            # Check duration field
            if is_non_english_text(story.other_params.get("duration")):
                offending_fields.append("other_params.duration")

        if not offending_fields:
            skipped.append(story.id)
            continue

        # ---------- GET SOURCE LANGUAGE ----------
        chat_session = ChatSession.objects.filter(
            session=story.session
        ).only("language").first()

        source_language = chat_session.language if chat_session else "en"

        # ❌ HARD FAIL RULE
        if source_language == "en":
            failed.append({
                "story_id": story.id,
                "reason": "Non-English detected but ChatSession.language = en",
                "fields": offending_fields
            })
            continue

        # ---------- GET VOICE PROVIDERS ----------
        # Get company_bot from chat_session if available
        company_bot = chat_session.company_bot if chat_session else None

        translation_provider = Voice.objects.filter(
            type=VoiceType.TextToText,
            language=source_language
        )
        if company_bot:
            translation_provider = translation_provider.filter(company_bot=company_bot)
        translation_provider = translation_provider.first()

        transliteration_provider = Voice.objects.filter(
            type=VoiceType.Transliterate,
            language=source_language
        )
        if company_bot:
            transliteration_provider = transliteration_provider.filter(company_bot=company_bot)
        transliteration_provider = transliteration_provider.first()

        updated = False
        other_params = story.other_params or {}

        # ---------- TRANSLATE MAIN STORY FIELDS ----------
        if is_non_english_text(story.title):
            story.title = translate_field(
                voice_provider=translation_provider,
                message_body=story.title,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.content):
            story.content = translate_field(
                voice_provider=translation_provider,
                message_body=story.content,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.objective):
            story.objective = translate_field(
                voice_provider=translation_provider,
                message_body=story.objective,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.impact):
            story.impact = translate_field(
                voice_provider=translation_provider,
                message_body=story.impact,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.micro_improvement):
            story.micro_improvement = translate_field(
                voice_provider=translation_provider,
                message_body=story.micro_improvement,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.tweet):
            story.tweet = translate_field(
                voice_provider=translation_provider,
                message_body=story.tweet,
                target_language="en",
                source_language=source_language
            )
            updated = True

        if is_non_english_text(story.blurb):
            story.blurb = translate_field(
                voice_provider=translation_provider,
                message_body=story.blurb,
                target_language="en",
                source_language=source_language
            )
            updated = True

        # ---------- HANDLE ACTION_STEPS ----------
        if isinstance(story.action_steps, str):
            if is_non_english_text(story.action_steps):
                story.action_steps = translate_field(
                    voice_provider=translation_provider,
                    message_body=story.action_steps,
                    target_language="en",
                    source_language=source_language
                )
                updated = True
        elif isinstance(story.action_steps, list):
            new_action_steps = []
            for step in story.action_steps:
                if step and is_non_english_text(step):
                    step = translate_field(
                        voice_provider=translation_provider,
                        message_body=step,
                        target_language="en",
                        source_language=source_language
                    )
                    updated = True
                new_action_steps.append(step)
            story.action_steps = new_action_steps

        # ---------- TRANSLITERATE LOCATION (main field) ----------
        if is_non_english_text(story.location):
            result = transliterate_text(
                voice_provider=transliteration_provider,
                message_body=story.location,
                target_language="en",
                source_language=source_language,
                is_sentence=" " in story.location
            )
            story.location = get_transliteration_output(result)
            updated = True

        # ---------- TRANSLITERATE PERSONAL INFO IN OTHER_PARAMS ----------
        transliteration_fields = ["user_name", "location", "organization", "designation"]
        for field in transliteration_fields:
            val = other_params.get(field)
            if val and is_non_english_text(val):
                result = transliterate_text(
                    voice_provider=transliteration_provider,
                    message_body=val,
                    target_language="en",
                    source_language=source_language,
                    is_sentence=" " in val
                )
                other_params[field] = get_transliteration_output(result)
                updated = True

        # ---------- TRANSLATE DURATION ----------
        duration = other_params.get("duration")
        if duration and is_non_english_text(duration):
            other_params["duration"] = translate_field(
                voice_provider=translation_provider,
                message_body=duration,
                target_language="en",
                source_language=source_language
            )
            updated = True

        # ---------- SAVE ----------
        if updated:
            story.other_params = other_params
            story.language = "en"
            story.save(update_fields=[
                "title", "content", "objective", "impact",
                "micro_improvement", "tweet", "blurb", "location",
                "action_steps", "other_params", "language"
            ])

            fixed.append({
                "story_id": story.id,
                "source_language": source_language,
                "fields": offending_fields
            })

    # ---------- WRITE REPORT ----------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("GUEST MI STORY FIX REPORT\n")
        f.write(f"Generated at: {datetime.utcnow().isoformat()} UTC\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total stories processed: {total}\n")
        f.write(f"Fixed: {len(fixed)}\n")
        f.write(f"Failed: {len(failed)}\n")
        f.write(f"Skipped (already English): {len(skipped)}\n\n")

        if failed:
            f.write("---- FAILED (Non-English with source_language=en) ----\n")
            for item in failed:
                f.write(f"Story ID: {item['story_id']}\n")
                f.write(f"Reason: {item['reason']}\n")
                f.write("Fields with non-English text:\n")
                for field in item["fields"]:
                    f.write(f"  - {field}\n")
                f.write("\n")

        if fixed:
            f.write("---- FIXED ----\n")
            for item in fixed:
                f.write(f"Story ID: {item['story_id']} | source_language={item['source_language']}\n")
                f.write("Fields that were fixed:\n")
                for field in item["fields"]:
                    f.write(f"  - {field}\n")
                f.write("\n")

        if skipped:
            f.write("---- SKIPPED (Already in English) ----\n")
            f.write(f"Story IDs: {', '.join(map(str, skipped[:50]))}")
            if len(skipped) > 50:
                f.write(f"... and {len(skipped) - 50} more\n")
            f.write("\n")

    print("=" * 70)
    print("Guest MI Story Fix Completed")
    print("=" * 70)
    print(f"Total stories processed: {total}")
    print(f"Fixed: {len(fixed)}")
    print(f"Failed: {len(failed)}")
    print(f"Skipped (already English): {len(skipped)}")
    print(f"Report saved to: {OUTPUT_FILE}")
    print("=" * 70)

    return {
        "total": total,
        "fixed": len(fixed),
        "failed": len(failed),
        "skipped": len(skipped),
        "report_file": OUTPUT_FILE
    }

