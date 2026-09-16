from celery import shared_task
from chatbot.services.core.bot_service_factory import BotServiceFactory
from chatbot.services.core.orchestrator import ChatOrchestrator
import logging


logger = logging.getLogger('django')

@shared_task
def get_oneshot_guest_response(channel_name, session_id, profile_id, route):
    """One-shot bot task"""
    extra_params = {
        'assistant_route': '/oneshot_guest_assistant',
        'validator_route': '/oneshot_guest_validator'
    }
    bot_strategy = BotServiceFactory.create_bot_service(
        bot_type='oneshot', route='/oneshot_guest', extra_params=extra_params
    )
    orchestrator = ChatOrchestrator(bot_strategy=bot_strategy)
    return orchestrator.process_chat_request(
        channel_name=channel_name, session_id=session_id, profile_id=profile_id,
        language=route
    )
