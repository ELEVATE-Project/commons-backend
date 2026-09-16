from chatbot.models import CompanyChat, ChatSession, CompanyBot
from chatbot.utils.audio_provider_utils import text_translate_provider
from django.db.models import F
import logging

logger = logging.getLogger('django')


def get_untranslated_bot_chats():
    """
    Returns CompanyChat rows where:
      - receiver_id = 1
      - session exists in ChatSession (inner join)
      - translated_message == message (no real translation happened)
    """
    valid_sessions = ChatSession.objects.filter(
        session_type='telangana-ptm-pilot'
    ).exclude(language='en').values_list('session', flat=True)

    chats = CompanyChat.objects.filter(
        receiver_id=1,
        session__in=valid_sessions,
        translated_message=F('message')
    )

    return chats


def print_untranslated_bot_chats():
    chats = get_untranslated_bot_chats()
    print(f"Total untranslated bot chats: {chats.count()}")
    for chat in chats:
        print(f"ID: {chat.id} | Session: {chat.session} | Message: {chat.message[:80]}")


def translate_untranslated_bot_chats():
    company_bot = CompanyBot.objects.filter(route='/classify-school-telangana-ptm').first()
    if not company_bot:
        logger.error("CompanyBot with route='/telangana_ptm_pilot' not found")
        return

    session_language_map = {
        s.session: s.language
        for s in ChatSession.objects.filter(
            session_type='telangana-ptm-pilot'
        ).exclude(language='en')
    }

    chats = get_untranslated_bot_chats()
    total = chats.count()
    print(f"Translating {total} chats...")

    success, failed = 0, 0
    for chat in chats:
        source_language = session_language_map.get(chat.session)
        if not source_language:
            logger.warning(f"No language found for session {chat.session}, skipping chat {chat.id}")
            failed += 1
            continue

        response = text_translate_provider(
            message_body=chat.message,
            target_language='en',
            source_language=source_language,
            company_bot=company_bot,
        )

        if response.get('status') == 200 and response.get('content') != chat.message:
            chat.translated_message = response['content']
            chat.save(update_fields=['translated_message'])
            success += 1
        else:
            logger.error(f"Translation failed for chat {chat.id}: {response.get('content')}")
            failed += 1

    print(f"Done. Success: {success}, Failed: {failed}")
