from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.strategies.base_strategy import BotStrategy


class GuidedGuestBotStrategy(BotStrategy):
    """Strategy for guided guest bot functionality"""

    def get_default_route(self):
        return '/guided_guest'

    def get_handler_type(self):
        return 'guided_guest'

    def process_session(self, session_data, **kwargs):
        """Handle guided guest specific session processing"""
        chat_session = session_data['chat_session']
        company_chats = session_data['company_chats']
        profile = session_data['profile']
        company_bot = session_data['company_bot']

        # Increment step for new profiles
        # if company_chats and len(company_chats) < 2 and profile and profile.first_name:
        #     chat_session.current_step += 1
        #     chat_session.save()

        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, step=chat_session.current_step
            )
            return {'state_machine': state_machine}
        except Exception as e:
            return {'error': f"State machine error: {e}"}

    def get_response(self, **kwargs):
        """Get guided guest bot response using handler"""
        return self.response_handler.handle_response(**kwargs)
