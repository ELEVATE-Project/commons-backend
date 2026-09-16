import traceback
import logging
from .base_service import BaseChatService
from .prompt_builder import PromptBuilder
from .message_handler import MessageHandler
from chatbot.celery_tasks.handle_message import translate_and_send_message

logger = logging.getLogger('django')


class ChatOrchestrator:
    """Main orchestrator for chat processing"""

    def __init__(self, bot_strategy):
        self.bot_strategy = bot_strategy
        self.base_service = BaseChatService()
        self.prompt_builder = PromptBuilder()
        self.message_handler = MessageHandler()

    def process_chat_request(self, channel_name, session_id, profile_id, language):
        """Main processing method"""
        try:
            # Get session data
            session_data = self.base_service.get_session_data(
                session_id=session_id, profile_id=profile_id, bot_route=self.bot_strategy.get_route()
            )

            # Get bot vernacular and intro
            bot_vernacular, intro_mssg = self.base_service.get_bot_vernacular_and_intro(
                company_bot=session_data['company_bot'], profile=session_data['profile']
            )

            # Get user profile info (for one-shot bots)
            other_info = self.base_service.get_user_profile_info(profile=session_data['profile'])
            # Prepare initial messages
            messages = self.message_handler.prepare_messages(
                company_bot=session_data['company_bot'], company_chats=session_data['company_chats'],
                intro_mssg=intro_mssg, other_info=other_info
            )

            # Process session based on strategy
            session_result = self.bot_strategy.process_session(
                session_data, intro_mssg=intro_mssg, other_info=other_info, messages=messages
            )

            if session_result.get('error'):
                return self._handle_error_response(
                    error_msg=session_result['error'], channel_name=channel_name, language=language,
                    chat_session=session_data['chat_session'], company_bot=session_data['company_bot']
                )

            state_machine = session_result.get('state_machine', None)

            # Get filtered chats
            temp_company_chats = self.message_handler.get_filtered_chats(
                session_id=session_id, state_machine=state_machine,
                company_chats=session_data['company_chats']
            )

            # Prepare temp messages
            temp_messages = self.message_handler.prepare_messages(
                company_bot=session_data['company_bot'], company_chats=temp_company_chats,
                intro_mssg=intro_mssg, other_info=other_info
            )

            # Build prompt
            prompt_to_use = self.prompt_builder.build_system_prompt(
                company_bot=session_data['company_bot'], state_machine=state_machine
            )

            # Get response using strategy
            response_params = {
                'system_prompt': prompt_to_use,
                'messages': messages,
                'company_bot': session_data['company_bot'],
                'session_id': session_id,
                'channel_name': channel_name,
                'language': language,
                'profile_id': profile_id,
                'temp_messages': temp_messages,
                'intro_mssg': intro_mssg,
            }

            # Add strategy-specific parameters
            if hasattr(self.bot_strategy, 'get_route') and 'oneshot' in self.bot_strategy.get_route():
                response_params['remaining_stages'] = session_result.get('remaining_stages', [])

            response = self.bot_strategy.get_response(**response_params)

            logger.info('Bot response: %s', response)
            return response

        except Exception as e:
            logger.error('Error in chat processing: %s', e, exc_info=True)
            traceback.print_exc()
            return None

    def _handle_error_response(self, error_msg, channel_name, language, chat_session, company_bot):
        """Handle error responses"""
        logger.info(f"Sending error message: {error_msg}")
        return translate_and_send_message(
            accumulated_message=error_msg, current_channel_name=channel_name, finish_reason="stop",
            current_step_number=chat_session.current_step, route=language, company_bot=company_bot
        )
