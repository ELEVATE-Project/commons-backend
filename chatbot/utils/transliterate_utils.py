from chatbot.models import VoiceProvider, VoiceType, LanguageMapping, CompanyBot
from chatbot.translate.ai4Bharat.transliterate import call_ai4bharat_transliterate_api
from chatbot.translate.custom.custom_llm import handle_custom_translation
from chatbot.translate.sarvam.sarvam import SarvamLanguageService
from chatbot.utils.audio_provider_utils import get_voice_provider


def transliterate_text(
        source_language, target_language, message_body, is_sentence=False, voice_provider=None, company_bot=None
):
    try:
        if not voice_provider and company_bot:
            voice_provider = get_voice_provider(
                company_bot=company_bot, voice_type=VoiceType.Transliterate, source_language=source_language,
                target_language=target_language
            )
        if voice_provider.provider == VoiceProvider.AI4Bharat:
            response = call_ai4bharat_transliterate_api(
                source_language=source_language, target_language=target_language, message_body=message_body,
                is_sentence=is_sentence
            )
        elif voice_provider.provider == VoiceProvider.SARVAM:
            service = SarvamLanguageService()
            response = service.transliterate(
                input_text=message_body, source_lang=LanguageMapping.get_mapped_language(source_language),
                target_lang=LanguageMapping.get_mapped_language(target_language),
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
            'content': message_body
        }


def get_transliteration_output(data):
    if data and isinstance(data, dict):
        data = data.get('content', [])
    if data and isinstance(data, list) and len(data) > 0:
        return data[0]

    return None
