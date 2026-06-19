from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.strategies.base_strategy import BotStrategy


class OneShotBotStrategy(BotStrategy):
    """Strategy for one-shot bot functionality"""

    def get_default_route(self):
        return '/oneshot_guest'

    def get_handler_type(self):
        return 'oneshot'

    def process_session(self, session_data, **kwargs):
        """Handle one-shot specific session processing"""
        from chatbot.utils.one_shot_utils import get_remaining_strands

        chat_session = session_data['chat_session']
        company_chats = session_data['company_chats']
        profile = session_data['profile']
        company_bot = session_data['company_bot']

        intro_mssg = kwargs.get('intro_mssg')
        other_info = kwargs.get('other_info')
        messages = kwargs.get('messages', [])

        if not chat_session.session_context:
            chat_session.session_context = {}

        remaining_stages = chat_session.session_context.get('remaining_stages')

        # Check if we need to get remaining stages
        if not remaining_stages and self._should_get_remaining_stages(intro_mssg, messages):

            remaining_stages_response = get_remaining_strands(
                messages=messages,
                company_chats=company_chats,
                oneshot_bot=company_bot,
                profile=profile,
                intro=intro_mssg,
                other_info=other_info,
                extra_params=self.extra_params
            )

            if remaining_stages_response and remaining_stages_response.get('error'):
                return {'error': remaining_stages_response.get('error')}

            remaining_stages = remaining_stages_response.get('remaining_stages', [])

            if remaining_stages and isinstance(remaining_stages, str):
                remaining_stages = []

            # Filter unwanted stages for existing profiles
            if profile and profile.first_name and remaining_stages:
                unwanted_stages = {'PERSONAL_INFO', 'LOCATION_INFO'}
                remaining_stages = [stage for stage in remaining_stages if stage not in unwanted_stages]

            remaining_stages.append('APPRECIATION')
            chat_session.session_context['remaining_stages'] = remaining_stages
            chat_session.save()

        # Get current stage and update session
        current_stage_name = remaining_stages[0]
        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, name=current_stage_name
            )
            chat_session.current_step = state_machine.step
            chat_session.save()
            return {'state_machine': state_machine, 'remaining_stages': remaining_stages}
        except Exception as e:
            return {'error': f"State machine error: {e}"}

    def _should_get_remaining_stages(self, intro_mssg, messages):
        """Check if remaining stages should be retrieved"""
        return (
                (intro_mssg is None and len(messages) < 2) or
                (intro_mssg is not None and len(messages) <= 3)
        )

    def get_response(self, **kwargs):
        """Get one-shot bot response using handler"""
        return self.response_handler.handle_response(**kwargs)
