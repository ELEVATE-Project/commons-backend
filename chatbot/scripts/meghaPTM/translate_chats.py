from chatbot.models import ChatSession, CompanyChat, CompanyBot, Voice, VoiceType, ChatType
from chatbot.utils.audio_provider_utils import text_translate_provider
from chatbot.utils.transliterate_utils import transliterate_text
from django.utils.timezone import make_aware
from datetime import datetime

###STEPS TO CALL:
    #CALL process_mega_ptm_chats() and this will run the whole script

def translate_field(voice_provider, message_body, target_language, source_language="en"):
    if not message_body:
        return message_body
    response = text_translate_provider(
        voice_provider=voice_provider, message_body=message_body, target_language=target_language,
        source_language=source_language
    )
    if response.get("status") == 200:
        return response.get("content")
    return message_body

def transliterate_field(voice_provider, message_body, target_language, source_language="en", is_sentence=False):
    if not message_body:
        return message_body
    response = transliterate_text(
        voice_provider=voice_provider, message_body=message_body, target_language=target_language,
        source_language=source_language, is_sentence=is_sentence
    )
    if response.get("status") == 200:
        res = response.get('content')
        if res and isinstance(res, list):
            res = res[0]
        return res
    return message_body


def process_mega_ptm_chats():
    start_time = make_aware(datetime(2025, 7, 1, 0, 0))
    end_time = make_aware(datetime(2025, 7, 17, 23, 59, 59))

    company_bot = CompanyBot.objects.get(route='/mega_ptm')
    translate_voice_provider = Voice.objects.filter(
        company_bot=company_bot, type=VoiceType.TextToText
    ).first()
    transliterate_voice_provider = Voice.objects.filter(
        company_bot=company_bot, type=VoiceType.Transliterate
    ).first()

    sessions = ChatSession.objects.filter(
        session_type=ChatType.megaPTM,
        created_at__range=(start_time, end_time)
    )

    for session in sessions:
        company_chats = CompanyChat.objects.filter(
            session=session.session
        ).order_by('created_at')

        if not company_chats.exists():
            continue

        # if company_chats.filter(translated_message__isnull=False).exclude(translated_message="").exists():
        #     print(f"Skipping session {session.session}: Already translated.")
        #     continue

        language = None
        for chat in company_chats:
            if chat.other_params and chat.other_params.get("language"):
                language = chat.other_params.get("language")
                break

        if not language or language == "en":
            print(f"Skipping session {session.session}: Language is 'en' or not found.")
            continue

        for chat in company_chats:
            sequence = chat.other_params.get("sequence") if chat.other_params else None
            print("len: ", len(chat.message.strip().split()))
            if len(chat.message.strip().split()) == 1 and sequence in [1, 2, 3] and chat.other_params.get('message_type') != "question":
                word_count = len(chat.message.strip().split())
                is_sentence = word_count > 1
                translated = transliterate_field(
                    voice_provider=transliterate_voice_provider, message_body=chat.message,
                    target_language="en", source_language=language, is_sentence=is_sentence
                )
            else:
                translated = translate_field(
                    voice_provider=translate_voice_provider, message_body=chat.message,
                    target_language="en", source_language=language
                )

            chat.translated_message = translated
            chat.save(update_fields=["translated_message"])
            print(f"✅ Session {session.session} | Chat ID {chat.id} translated.")

    print("✅ Mega PTM translation process complete.")
