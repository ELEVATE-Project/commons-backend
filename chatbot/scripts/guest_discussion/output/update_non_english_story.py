import re
import logging
from datetime import datetime

from chatbot.models import (
    Story, ChatSession, SessionFlowName, Voice, VoiceType
)
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.transliterate_utils import transliterate_text, get_transliteration_output

logger = logging.getLogger("django")

OUTPUT_FILE = "guest_discussion_fix_report.txt"

# ---------- LANGUAGE DETECTION ----------
ENGLISH_LETTER_REGEX = re.compile(r'[A-Za-z]')
ANY_LETTER_REGEX = re.compile(r'[A-Za-z\u00C0-\u024F\u0900-\u097F]')


def is_non_english_text(text):
    if not text or not isinstance(text, str):
        return False
    # Ignore numbers / dates / symbols
    if not ANY_LETTER_REGEX.search(text):
        return False
    return not ENGLISH_LETTER_REGEX.search(text)


def find_non_english_in_json(obj, path="other_params"):
    found = []

    if isinstance(obj, str):
        if is_non_english_text(obj):
            found.append(path)
        return found

    if isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(find_non_english_in_json(k, f"{path}.{k} (key)"))
            found.extend(find_non_english_in_json(v, f"{path}.{k}"))

    if isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(find_non_english_in_json(item, f"{path}[{i}]"))

    return found


# ---------- MAIN SCRIPT ----------
def fix_guest_discussion_stories():
    stories = Story.objects.filter(
        other_params__flow=SessionFlowName.GuestDiscussion
    )

    total = stories.count()
    fixed = []
    failed = []
    skipped = []

    for story in stories:
        offending_fields = []

        # 🔹 CHECK STORY.LOCATION
        if is_non_english_text(story.location):
            offending_fields.append("story.location")
        if is_non_english_text(story.title):
            offending_fields.append("story.title")

        # 🔹 CHECK OTHER_PARAMS
        if story.other_params:
            offending_fields.extend(
                find_non_english_in_json(story.other_params)
            )

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

        # ---------- VOICE PROVIDERS ----------
        translation_provider = Voice.objects.filter(
            type=VoiceType.TextToText,
            language=source_language
        ).first()

        transliteration_provider = Voice.objects.filter(
            type=VoiceType.Transliterate,
            language=source_language
        ).first()

        updated = False
        other_params = story.other_params or {}

        # ---------- FIX STORY.LOCATION ----------
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

        # ---------- TRANSLATE STORY.TITLE ----------
        if is_non_english_text(story.title):
            story.title = translate_field(
                voice_provider=translation_provider,
                message_body=story.title,
                target_language="en",
                source_language=source_language
            )
            updated = True

        # ---------- TRANSLATE FIELDS ----------
        for field in ["remarks"]:
            val = other_params.get(field)
            if val and is_non_english_text(val):
                other_params[field] = translate_field(
                    voice_provider=translation_provider,
                    message_body=val,
                    target_language="en",
                    source_language=source_language
                )
                updated = True

        # ---------- TRANSLATE LIST FIELDS ----------
        for list_field in ["challenges_faced", "solutions_discussed"]:
            values = other_params.get(list_field)
            if isinstance(values, list):
                new_vals = []
                for v in values:
                    if v and is_non_english_text(v):
                        v = translate_field(
                            voice_provider=translation_provider,
                            message_body=v,
                            target_language="en",
                            source_language=source_language
                        )
                        updated = True
                    new_vals.append(v)
                other_params[list_field] = new_vals

        # ---------- TRANSLITERATION HELPER ----------
        def transliterate(obj, key):
            nonlocal updated
            val = obj.get(key)
            if val and is_non_english_text(val):
                result = transliterate_text(
                    voice_provider=transliteration_provider,
                    message_body=val,
                    target_language="en",
                    source_language=source_language,
                    is_sentence=" " in val
                )
                obj[key] = get_transliteration_output(result)
                updated = True

        for key in ["user_name", "organization", "location"]:
            transliterate(other_params, key)

        for nested in ["pri_member", "school_representative"]:
            data = other_params.get(nested)
            if isinstance(data, dict):
                transliterate(data, "name")
                transliterate(data, "designation")

        # ---------- SAVE ----------
        if updated:
            story.other_params = other_params
            story.language = "en"
            story.save(update_fields=["location", "title", "other_params", "language"])

            fixed.append({
                "story_id": story.id,
                "source_language": source_language,
                "fields": offending_fields
            })

    # ---------- WRITE REPORT ----------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("GUEST DISCUSSION FIX REPORT\n")
        f.write(f"Generated at: {datetime.utcnow().isoformat()} UTC\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total stories processed: {total}\n")
        f.write(f"Fixed: {len(fixed)}\n")
        f.write(f"Failed: {len(failed)}\n")
        f.write(f"Skipped: {len(skipped)}\n\n")

        f.write("---- FAILED ----\n")
        for item in failed:
            f.write(f"Story ID: {item['story_id']}\n")
            for field in item["fields"]:
                f.write(f"  - {field}\n")
            f.write("\n")

        f.write("---- FIXED ----\n")
        for item in fixed:
            f.write(f"Story ID: {item['story_id']} | source_language={item['source_language']}\n")
            for field in item["fields"]:
                f.write(f"  - {field}\n")
            f.write("\n")

    print("====================================")
    print("Guest Discussion Fix Completed")
    print("Total:", total)
    print("Fixed:", len(fixed))
    print("Failed:", len(failed))
    print("Skipped:", len(skipped))
    print("Report saved to:", OUTPUT_FILE)
    print("====================================")


def fix_guest_discussion_stories_by_id(story_ids=None, session_id=None):
    stories = Story.objects.filter(
        other_params__flow=SessionFlowName.GuestDiscussion
    )

    # Apply filters based on parameters
    if story_ids is not None:
        # Handle single ID or list of IDs
        if not isinstance(story_ids, list):
            story_ids = [story_ids]
        stories = stories.filter(id__in=story_ids)
        print(f"🔍 Processing specific story IDs: {story_ids}")
    elif session_id is not None:
        stories = stories.filter(session=session_id)
        print(f"🔍 Processing stories for session: {session_id}")
    else:
        print("🔍 Processing ALL Guest Discussion stories")

    total = stories.count()

    if total == 0:
        print("❌ No stories found with the given criteria")
        return

    print(f"📊 Found {total} stories to process\n")

    fixed = []
    failed = []
    skipped = []

    # ---------- MAIN PROCESSING LOOP ----------
    for story in stories:
        print(f"Processing story {story.id}...", end=" ")

        offending_fields = []

        # 🔹 CHECK STORY.LOCATION
        if is_non_english_text(story.location):
            offending_fields.append("story.location")
        if is_non_english_text(story.title):
            offending_fields.append("story.title")

        # 🔹 CHECK OTHER_PARAMS
        if story.other_params:
            offending_fields.extend(
                find_non_english_in_json(story.other_params)
            )

        if not offending_fields:
            skipped.append(story.id)
            print("✓ Skipped (no non-English)")
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
            print("✗ Failed (source language is English)")
            continue

        # ---------- VOICE PROVIDERS ----------
        translation_provider = Voice.objects.filter(
            type=VoiceType.TextToText,
            language=source_language
        ).first()

        transliteration_provider = Voice.objects.filter(
            type=VoiceType.Transliterate,
            language=source_language
        ).first()

        updated = False
        other_params = story.other_params or {}

        # ---------- FIX STORY.LOCATION ----------
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

        # ---------- TRANSLATE STORY.TITLE ----------
        if is_non_english_text(story.title):
            story.title = translate_field(
                voice_provider=translation_provider,
                message_body=story.title,
                target_language="en",
                source_language=source_language
            )
            updated = True

        # ---------- TRANSLATE FIELDS ----------
        for field in ["remarks"]:
            val = other_params.get(field)
            if val and is_non_english_text(val):
                other_params[field] = translate_field(
                    voice_provider=translation_provider,
                    message_body=val,
                    target_language="en",
                    source_language=source_language
                )
                updated = True

        # ---------- TRANSLATE LIST FIELDS ----------
        for list_field in ["challenges_faced", "solutions_discussed"]:
            values = other_params.get(list_field)
            if isinstance(values, list):
                new_vals = []
                for v in values:
                    if v and is_non_english_text(v):
                        v = translate_field(
                            voice_provider=translation_provider,
                            message_body=v,
                            target_language="en",
                            source_language=source_language
                        )
                        updated = True
                    new_vals.append(v)
                other_params[list_field] = new_vals

        # ---------- TRANSLITERATION HELPER ----------
        def transliterate(obj, key):
            nonlocal updated
            val = obj.get(key)
            if val and is_non_english_text(val):
                result = transliterate_text(
                    voice_provider=transliteration_provider,
                    message_body=val,
                    target_language="en",
                    source_language=source_language,
                    is_sentence=" " in val
                )
                obj[key] = get_transliteration_output(result)
                updated = True

        for key in ["user_name", "organization", "location"]:
            transliterate(other_params, key)

        for nested in ["pri_member", "school_representative"]:
            data = other_params.get(nested)
            if isinstance(data, dict):
                transliterate(data, "name")
                transliterate(data, "designation")

        # ---------- SAVE ----------
        if updated:
            story.other_params = other_params
            story.language = "en"
            story.save(update_fields=["location", "title", "other_params", "language"])

            fixed.append({
                "story_id": story.id,
                "source_language": source_language,
                "fields": offending_fields
            })
            print("✓ Fixed")
        else:
            print("⚠️ No updates needed")

    # ---------- WRITE REPORT ----------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("GUEST DISCUSSION FIX REPORT\n")
        f.write(f"Generated at: {datetime.utcnow().isoformat()} UTC\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total stories processed: {total}\n")
        f.write(f"Fixed: {len(fixed)}\n")
        f.write(f"Failed: {len(failed)}\n")
        f.write(f"Skipped: {len(skipped)}\n\n")

        f.write("---- FAILED ----\n")
        for item in failed:
            f.write(f"Story ID: {item['story_id']}\n")
            f.write(f"Reason: {item['reason']}\n")
            for field in item["fields"]:
                f.write(f"  - {field}\n")
            f.write("\n")

        f.write("---- FIXED ----\n")
        for item in fixed:
            f.write(f"Story ID: {item['story_id']} | source_language={item['source_language']}\n")
            for field in item["fields"]:
                f.write(f"  - {field}\n")
            f.write("\n")

        f.write("---- SKIPPED ----\n")
        for story_id in skipped:
            f.write(f"Story ID: {story_id}\n")

    print("\n" + "=" * 50)
    print("📋 Guest Discussion Fix Completed")
    print("=" * 50)
    print(f"Total: {total}")
    print(f"✅ Fixed: {len(fixed)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"⏭️  Skipped: {len(skipped)}")
    print(f"📄 Report saved to: {OUTPUT_FILE}")
    print("=" * 50)

    return {
        "fixed": fixed,
        "failed": failed,
        "skipped": skipped,
        "total": total
    }

