from pyexpat.errors import messages

from chatbot.models import ChatStatus, Profile, CompanyChat
from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.response_handlers.base_response_handler import BaseResponseHandler
from chatbot.utils.chaupal_question import get_chaupal_challenge_response, get_chaupal_solution_response
from chatbot.utils.shiksha_chaupal.date_utils import handle_date_prompt
import logging

logger = logging.getLogger('django')


class GuestDiscussionResponseHandler(BaseResponseHandler):
    """Response handler for guest discussion bot"""

    def check_early_return(self, chat_session, **kwargs):
        """Check for EVENT state early return"""
        company_bot = kwargs['company_bot']

        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, step=chat_session.current_step
            )
            print("Current step in early func: ", state_machine.name)
            # Special handling for EVENT state
            if state_machine and state_machine.name == 'EVENT':
                print("Here inside")
                return self._handle_event_state(chat_session=chat_session, state_machine=state_machine, **kwargs)
        except Exception as e:
            print("Error: ", e)
            logger.error(f"Error in check_early_return: {e}")

        return None

    def _handle_event_state(self, chat_session, state_machine, **kwargs):
        """Handle EVENT state with date prompt"""
        intro_mssg = kwargs.get('intro_mssg')
        profile = kwargs.get('profile')
        other_info = kwargs.get('other_info')
        channel_name = kwargs['channel_name']
        language = kwargs['language']
        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        profile_id = kwargs['profile_id']
        print("Before date fun")
        company_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
        bot_question = handle_date_prompt(
            intro_mssg=intro_mssg,
            profile=profile,
            company_chats=company_chats,
            other_info=other_info
        )
        print("DATE RES: ", bot_question)
        if bot_question is None:
            bot_question = self.default_error_message

        if bot_question == '':
            # Return special flag to skip LLM call
            return {'skip_llm': True}
        else:
            # Send the date prompt response
            translated_message = self.translate_message(
                message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
                language=language, company_bot=company_bot
            )

            self.save_message(
                session_id=session_id, profile_id=profile_id, message=bot_question, chunks=None,
                status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=state_machine.name
            )

            return bot_question

    def get_messages_for_llm(self, **kwargs):
        """Use temp_messages if available, otherwise original messages"""
        temp_messages = kwargs.get('temp_messages')
        messages=kwargs.get('messages')
        return temp_messages if temp_messages else messages

    def _send_db_question(self, bot_question, chat_session, chunks, **kwargs):
        """Send bot question from database for NON_LLM operations"""
        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        channel_name = kwargs['channel_name']
        language = kwargs['language']
        profile_id = kwargs['profile_id']
        
        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, step=chat_session.current_step
            )
        except CompanyStateMachine.DoesNotExist:
            logger.error(f"State machine not found for step {chat_session.current_step}")
            return self.default_error_message
        
        chat_status = self.get_chat_status(
            state_machine=state_machine, company_bot=company_bot
        )
        
        # Translate and send to WebSocket
        translated_message = self.translate_message(
            message=bot_question,
            channel_name=channel_name,
            step_number=chat_session.current_step,
            language=language,
            company_bot=company_bot
        )
        
        # Save to database with metadata indicating this is a NON_LLM question from DB
        self.save_message(
            session_id=session_id,
            profile_id=profile_id,
            message=bot_question,
            chunks=chunks,
            status=chat_status,
            translated_message=translated_message,
            stage=state_machine.name,
            other_params={
                'message_type': 'question',
                'operation_type': 'non_llm',
                'source': 'database'
            }
        )
        
        logger.info(f"Sent NON_LLM bot question from DB for state: {state_machine.name}")
        return bot_question


    def process_response(self, response, chat_session, chunks, **kwargs):
        """Process guest discussion response"""
        skip_llm_call = kwargs.get('skip_llm', False)
        send_bot_question = kwargs.get('send_bot_question', False)

        # Handle NON_LLM operation type - send bot_question directly from database
        if send_bot_question and skip_llm_call:
            bot_question = kwargs.get('bot_question_from_db')
            if bot_question:
                return self._send_db_question(
                    bot_question=bot_question,
                    chat_session=chat_session,
                    chunks=chunks,
                    **kwargs
                )

        current_step = chat_session.current_step
        if skip_llm_call:
            is_function_call = True
        else:
            is_function_call = self.is_function_call(response=response)

        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        language = kwargs['language']
        profile_id = kwargs['profile_id']
        channel_name = kwargs['channel_name']
        skip_next_stage=kwargs.get('skip_next_stage', False)
        target_stage=kwargs.get('target_stage', False)
        chat_messages=self.get_messages_for_llm(**kwargs)

        if is_function_call:
            return self._handle_function_call(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, messages=chat_messages, skip_next_stage=skip_next_stage, target_stage=target_stage
            )
        else:
            return self._handle_regular_response(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, current_step=current_step
            )


    def _handle_function_call(self, response, chat_session, company_bot,
                              session_id, channel_name, language, profile_id, chunks, messages, skip_next_stage,
                              target_stage):
        """Handle function call for guided guest"""
        if skip_next_stage:
            if target_stage and isinstance(target_stage, int):
                chat_session.current_step = target_stage
            else:
                chat_session.current_step += 2
        else:
            chat_session.current_step += 1
        chat_session.save()

        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, step=chat_session.current_step
        )
        bot_question = state_machine.bot_question

        # Check if this is a NON_LLM state - if so, just use bot_question from DB
        is_non_llm = False
        if hasattr(state_machine, 'operation_type'):
            from chatbot.models.enums import OperationTypeChoices
            if state_machine.operation_type == OperationTypeChoices.NON_LLM:
                is_non_llm = True
                logger.info(f"State {state_machine.name} is NON_LLM, using bot_question from DB")

        # Only process CHALLENGES and SOLUTIONS for LLM states
        if not is_non_llm:
            if state_machine.name == 'CHALLENGES':
                challenge_res = get_chaupal_challenge_response(messages=messages)
                if challenge_res and isinstance(challenge_res, str):
                    bot_question = challenge_res
                else:
                    bot_question = self.default_error_message

            elif state_machine.name == 'SOLUTIONS':
                solution_res = get_chaupal_solution_response(messages=messages)

                if solution_res in ["", '', '""', None]:
                    # Skip to next state
                    chat_session.current_step += 1
                    chat_session.save()
                    state_machine = CompanyStateMachine.objects.get(
                        company_bot=company_bot, step=chat_session.current_step
                    )
                    bot_question = state_machine.bot_question
                elif solution_res and isinstance(solution_res, str):
                    bot_question = solution_res
                else:
                    bot_question = self.default_error_message

        chat_status = self.get_chat_status(state_machine=state_machine, company_bot=company_bot)

        translated_message = self.translate_message(
            message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
            language=language, company_bot=company_bot
        )

        # Prepare other_params with metadata
        other_params = {}
        if is_non_llm:
            other_params = {
                'message_type': 'question',
                'operation_type': 'non_llm',
                'source': 'database'
            }

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=bot_question, chunks=chunks,
            status=chat_status, translated_message=translated_message, stage=state_machine.name,
            other_params=other_params if other_params else None
        )

        return response

    def _handle_regular_response(self, response, chat_session, company_bot,
                                 session_id, channel_name, language, profile_id,
                                 chunks, current_step):
        """Handle regular response for guided guest"""
        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, step=chat_session.current_step
        )

        translated_message = self.translate_message(
            message=response, channel_name=channel_name, step_number=current_step,
            language=language, company_bot=company_bot
        )

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=response, chunks=chunks,
            status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=state_machine.name
        )

        return response
