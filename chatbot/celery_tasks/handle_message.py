from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from chatbot.models import RouteLanguageChoices, Voice, VoiceType
from chatbot.utils.audio_provider_utils import text_translate_provider
import logging


channel_layer = get_channel_layer()
logger = logging.getLogger('django')


def translate_and_send_message(
        accumulated_message, current_channel_name, current_step_number, finish_reason, route, company_bot,
        extra_content=None
):

    if route != 'en' and accumulated_message and accumulated_message!= '':
        # target_language_code = get_language_code_from_route(route)
        logger.info(f"target_language_code date: %s", route)
        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=route
        ).first()

        response = text_translate_provider(
            voice_provider=voice_provider, message_body=accumulated_message, target_language=route,
            source_language='en'
        )
        if response.get('status') == 200:
            translated_messages =  response.get('content')
        else:
            translated_messages = accumulated_message

        async_to_sync(channel_layer.send)(
            current_channel_name,
            {
                "type": "chat.message",
                "text": {
                    "msg": translated_messages,
                    "source": "bot",
                    "finish_reason": finish_reason,
                    "step": current_step_number,
                    "extra_content": extra_content
                },
            },
        )
        logger.info(f"Translated message: %s", translated_messages)
        return translated_messages
    else:
        logger.info(f"Sending  accumulated_message: %s", accumulated_message)
        async_to_sync(channel_layer.send)(
            current_channel_name,
            {
                "type": "chat.message",
                "text": {
                    "msg": accumulated_message,
                    "source": "bot",
                    "finish_reason": finish_reason,
                    "step": current_step_number,
                    "extra_content": extra_content
                },
            },
        )
        return None

def get_language_code_from_route(route):
    route = route.strip()
    for choice in RouteLanguageChoices:
        if choice.value == route:
            return choice.value
    return RouteLanguageChoices.ENGLISH.value
