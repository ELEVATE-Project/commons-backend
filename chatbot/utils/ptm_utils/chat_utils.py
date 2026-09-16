from chatbot.models import ChatType, Profile, CompanyBot, ChatSession, CompanyChat, Voice, VoiceType, TextConversionType
from django.db import transaction
from chatbot.utils.audio_provider_utils import text_translate_provider
from chatbot.utils.transliterate_utils import transliterate_text
import logging

logger = logging.getLogger('django')


def get_bot_from_flow(flow):
    route = None
    if flow == ChatType.megaPTM:
        route = '/mega_ptm'
    else:
        route = '/common_bot'

    return route


def save_question_answer_utils(
    profile_id, flow, session, sequence, status, language, question_id,
    sent_at, question, translated_message, answer, audio_file, answer_id,
    service
):
    try:
        user_translated_msg=None
        with transaction.atomic():
            logger.info("Started saving Q&A for session %s", session)
            ai_user = Profile.objects.get(id=1)
            user_profile = Profile.objects.get(id=profile_id)

            route = get_bot_from_flow(flow=flow)
            company_bot = CompanyBot.objects.filter(route=route).first()
            if not company_bot:
                logger.error("No bots found for route %s", route)
                return {"error": "No bots found for this flow", "status": 404}

            print("language: ", language)
            print("service: ", service)
            if language and language != 'en' and service and answer:
                if service == TextConversionType.TRANSLITERATE:
                    transliterate_voice_provider = Voice.objects.filter(
                        company_bot=company_bot,
                        type=VoiceType.Transliterate,
                        language=language
                    ).first()
                    is_sentence = ' ' in answer
                    response = transliterate_text(
                        voice_provider=transliterate_voice_provider, source_language=language, target_language='en',
                        message_body=answer, is_sentence=is_sentence
                    )
                    print("Trans response: ", response)
                    if response and response.get('content'):
                        content = response.get('content')
                        print("Trans content: ", content)
                        if content and isinstance(content, list) and len(content) > 0:
                            content = content[0]
                        user_translated_msg = content
                else:
                    voice_provider = Voice.objects.filter(
                        company_bot=company_bot,
                        type=VoiceType.TextToText,
                        language=language
                    ).first()
                    response = text_translate_provider(
                        voice_provider=voice_provider, message_body=answer,
                        target_language='en', source_language=language
                    )

                    if response.get('status') == 200:
                        user_translated_msg = response.get('content')

            chat_session, created = ChatSession.objects.update_or_create(
                session=session,
                defaults={
                    "profile": user_profile,
                    "company_bot": company_bot,
                    "current_step": sequence,
                    "session_status": status,
                    "session_type": flow,
                    "language": language,
                }
            )
            logger.info("Chat session %s %s", "created" if created else "updated", session)

            other_params = {
                "language": language,
                "sent_at": sent_at,
                "sequence": sequence,
                "question_id": question_id,
            }

            question_params = {**other_params, "message_type": "question"}
            answer_params = {**other_params, "message_type": "answer", "answer_id": answer_id}

            CompanyChat.objects.update_or_create(
                session=session,
                source_msg_id=question_id,
                defaults={
                    "message": translated_message if language and language!='en' else question,
                    "status": status,
                    "sender": ai_user,
                    "receiver": user_profile,
                    "chunks": None,
                    "translated_message": question if language and language!='en' else translated_message,
                    "other_params": question_params,
                }
            )
            logger.info("Saved question with ID %s for session %s", question_id, session)

            existing_answer = CompanyChat.objects.filter(
                session=session, source_msg_id=answer_id
            ).first()
            if existing_answer and existing_answer.file_url and audio_file:
                audio_file = f"{existing_answer.file_url},{audio_file}" 

            CompanyChat.objects.update_or_create(
                session=session,
                source_msg_id=answer_id,
                defaults={
                    "message": answer,
                    "status": status,
                    "sender": user_profile,
                    "receiver": ai_user,
                    "chunks": None,
                    "translated_message": user_translated_msg,
                    "other_params": answer_params,
                    "file_url": audio_file
                }
            )
            logger.info("Saved answer with source_msg_id %s for session %s", sent_at, session)
            return {"message": "Message saved successfully!", "status": 200}

    except Profile.DoesNotExist:
        logger.error('Profile with id %s does not exist', profile_id, exc_info=True)
        return {"error": "Profile not found.", "status": 404}
    except Exception as e:
        logger.error('Error processing session %s: %s', session, e, exc_info=True)
        return {"error": str(e), "status": 500}
