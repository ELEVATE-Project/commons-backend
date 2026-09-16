from chatbot.models import VoiceProvider, LanguageMapping, Voice, VoiceType, CompanyBot
from chatbot.translate.ai4Bharat.speech_to_text import transcribe_ai4bharat_multiple_chunks
from chatbot.translate.ai4Bharat.text_to_speech import ai4bharat_text_speech
from chatbot.translate.ai4Bharat.text_to_text import call_ai4bharat_translation_api
from chatbot.translate.custom.custom_llm import handle_custom_translation
from chatbot.translate.google.google_stt import transcribe_multiple_languages_v2
from chatbot.translate.google.google_stt_v1 import transcribe_multiple_languages_v1
from chatbot.translate.google.google_translate import translate_text
from chatbot.translate.google.google_tts import google_text_to_speech
from chatbot.translate.openai.openai_stt import transcribe_audio
from chatbot.translate.sarvam.sarvam import SarvamLanguageService
from chatbot.translate.sarvam.speech_to_text import transcribe_sarvam_multiple_chunks
from chatbot.translate.sarvam.text_to_speech import sarvam_text_to_speech
from django.conf import settings
import logging


logger = logging.getLogger('django')


def get_voice_provider(company_bot, voice_type, source_language=None, target_language=None):
    """Return appropriate Voice provider preferring non-English language."""

    language = (
        target_language if target_language and target_language.lower() != "en"
        else source_language if source_language and source_language.lower() != "en"
        else "en"
    )

    voice = Voice.objects.filter(
        company_bot=company_bot,
        type=voice_type,
        language=language,
    ).first()

    if not voice and language != "en":
        voice = Voice.objects.filter(
            company_bot=company_bot,
            type=voice_type,
            language="en",
        ).first()

    return voice


def text_speech_provider(company_bot, text, source_language):
    voice_provider = get_voice_provider(
        company_bot=company_bot, voice_type=VoiceType.TextToSpeech, source_language=source_language
    )
    if not voice_provider:
        return {
            'status': 500,
            'content': "No voice configuration found!"
        }

    if voice_provider.provider == VoiceProvider.AI4Bharat:
        response = ai4bharat_text_speech(
            text=text, gender=voice_provider.gender, source_language=source_language,
            voice_provider=voice_provider
        )
    elif voice_provider.provider == VoiceProvider.GOOGLE:
        response = google_text_to_speech(
            message=text, language_code=LanguageMapping.get_mapped_language(source_language),
            voice_provider=voice_provider
        )
    elif voice_provider.provider == VoiceProvider.SARVAM:
        response = sarvam_text_to_speech(
            message=text, source_language=source_language, voice_provider=voice_provider
        )
    else:
        return {
            'status': 500,
            'content': "No provider found!"
        }

    return response


def speech_text_provider(company_bot, base64, audio_format, source_language):
    voice_provider = get_voice_provider(
        company_bot=company_bot, voice_type=VoiceType.SpeechToText, source_language=source_language
    )
    if not voice_provider:
        return {
            'status': 500,
            'content': "No voice configuration found!"
        }

    if voice_provider.provider == VoiceProvider.AI4Bharat:
        response = transcribe_ai4bharat_multiple_chunks(
            base64_audio_file=base64, source_language=source_language, audio_format=audio_format,
            voice_provider=voice_provider
        )
    elif voice_provider.provider == VoiceProvider.GOOGLE:
        if source_language == 'en':
            region = "US"
        else:
            region = "IN"

        secret = settings.SECRETS
        response = transcribe_multiple_languages_v2(
            project_id=secret.get('project_id'), audio_file=base64,
            language_codes=[LanguageMapping.get_mapped_language(source_language, region)],
            voice_provider=voice_provider
        )
    elif voice_provider.provider == VoiceProvider.OPENAI_WHISPER:
        response = transcribe_audio(
            base64_audio=base64, audio_format=audio_format, source_language=source_language,
            voice_provider=voice_provider
        )
    elif voice_provider.provider == VoiceProvider.SARVAM:
        response = transcribe_sarvam_multiple_chunks(
            base64_audio_file=base64, audio_format=audio_format,
            source_language=LanguageMapping.get_sarvam_language(source_language),
            voice_provider=voice_provider
        )

    else:
        return {
            'status': 500,
            'content': "No provider found!"
        }
    return response


def text_translate_provider(message_body, target_language, source_language, voice_provider=None, company_bot=None):
    try:
        if not voice_provider and company_bot:
            voice_provider = get_voice_provider(
                company_bot=company_bot, voice_type=VoiceType.TextToText, source_language=source_language,
                target_language=target_language
            )
        if voice_provider.provider == VoiceProvider.AI4Bharat:
            response = call_ai4bharat_translation_api(
                source_language=source_language, target_language=target_language, message_body=message_body,
                voice_provider=voice_provider
            )
        elif voice_provider.provider == VoiceProvider.GOOGLE:
            secret = settings.SECRETS
            response = translate_text(
                project_id=secret.get('project_id'), text=message_body,
                source_language_code=LanguageMapping.get_google_translate_language(source_language),
                target_language_code=LanguageMapping.get_google_translate_language(target_language),
                voice_provider=voice_provider
            )
        elif voice_provider.provider == VoiceProvider.SARVAM:
            service = SarvamLanguageService()
            response = service.translate(
                input_text=message_body,
                source_lang=LanguageMapping.get_sarvam_language(source_language),
                target_lang=LanguageMapping.get_sarvam_language(target_language),
                voice_provider=voice_provider
            )
        elif voice_provider.provider == VoiceProvider.CUSTOM_LLM:
            other = getattr(voice_provider, "other_params", {}) or {}
            route = other.get('route', "/transliterate_text")
            company_bot = CompanyBot.objects.filter(route=route).first()
            response = handle_custom_translation(
                message_body=message_body, source_language=LanguageMapping.get_mapped_language(source_language),
                target_language=LanguageMapping.get_mapped_language(target_language), company_bot=company_bot
            )
        else:
            return {
                'status': 500,
                'content': "No provider found!"
            }
        return response
    except Exception as e:
        return {
            'status': 500,
            'content': str(e)
        }
