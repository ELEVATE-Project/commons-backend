from abc import ABC, abstractmethod
from channels.layers import get_channel_layer
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.celery_tasks.handle_message import translate_and_send_message
from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import ChatSession, ChatStatus, LLMProvider, CompanyBotTypeChoices
from chatbot.models.company_models import CompanyStateMachine
from chatbot.models.enums import OperationTypeChoices
from chatbot.services.postprocessing.postprocessing_service import PostprocessingService
from chatbot.services.preprocessing.preprocessing_service import PreprocessingService
import logging

logger = logging.getLogger('django')
channel_layer = get_channel_layer()

class BaseResponseHandlerNew(ABC):
    """Base class for handling LLM responses with common functionality"""

    def __init__(self):
        self.default_error_message = 'I am sorry, I could not understood completely. Could you rephrase this please?'
        self.preprocessing_service = PreprocessingService()
        self.postprocessing_service = PostprocessingService()
        self.min_word_count = 3
        self.max_retry_attempts = 2

    def _is_response_too_short(self, response):
        """
        Check if response is too short (less than 3 words).
        Returns True if response needs to be regenerated.
        """
        try:
            if not response or response == '':
                return False

            if isinstance(response, dict):
                response_text = response.get('response', '')
                if not response_text:
                    return False
            else:
                response_text = str(response)

            response_text = response_text.strip()
            if not response_text:
                return False

            word_count = len(response_text.split())

            logger.info(f"Response word count: {word_count}, text: '{response_text[:100]}...'")

            if word_count < self.min_word_count:
                logger.info(f"Response too short: {word_count} words (minimum: {self.min_word_count})")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking response length: {e}")
            return False

    def is_non_llm_state(self, state_machine):
        return (
                state_machine
                and hasattr(state_machine, 'operation_type')
                and state_machine.operation_type == OperationTypeChoices.NON_LLM
        )

    def build_non_llm_function_call(self, state_machine):
        return {
            "toolUseId": "non_llm_auto",
            "name": "get_state_information",
            "input": {
                "next_state_name": state_machine.name,
                "reason": "NON_LLM auto transition"
            }
        }

    def handle_response(self, **kwargs):
        """Main response handling method"""
        # Extract common parameters
        session_id = kwargs['session_id']
        chat_session = ChatSession.objects.get(session=session_id)
        chunks = []
        is_function_call = False
        early_return = self.check_early_return(chat_session, **kwargs)
        if early_return is not None:
            if isinstance(early_return, str):
                return early_return
            elif isinstance(early_return, dict):
                if early_return.get('skip_llm', False):
                    kwargs['skip_llm'] = True
                else:
                    is_function_call = self.is_function_call(response=early_return)
            else:
                return early_return

        company_bot = kwargs.get('company_bot')
        try:
            state_machine = CompanyStateMachine.objects.filter(
                company_bot=company_bot, step=chat_session.current_step
            ).first()
        except Exception as e:
            logger.error(f"Error getting state machine: {e}")
            state_machine = None

        # Prepare original prompt
        original_prompt = kwargs.get('system_prompt', [])

        # Execute preprocessing if state machine exists
        preprocessing_result = {'action': 'continue', 'prompt': original_prompt}
        if state_machine:
            preprocessing_result = self.preprocessing_service.execute_preprocessing(
                state_machine, original_prompt, **kwargs
            )

        # Handle preprocessing results
        if preprocessing_result['action'] == 'skip':
            # Skip the current stage - move to next stage
            kwargs['skip_llm'] = True
            kwargs['skip_reason'] = 'preprocessing'
        elif preprocessing_result['action'] == 'continue':
            # Update prompt if it was enriched
            kwargs['system_prompt'] = preprocessing_result.get('prompt', original_prompt)

        response = None
        # Get LLM response
        if not kwargs.get('skip_llm', False):
            response = self.get_llm_response(**kwargs)
            print("before response: ", response)
            if response is None:
                if company_bot.bot_type == CompanyBotTypeChoices.STATE_MACHINE:
                    response = {
                        "toolUseId": "tooluse_fallback", "name": "get_state_information",
                        "input": {
                            "next_state_name": "SAMPLE",
                            "reason": "LLM returned no response"
                        }
                    }
                else:
                    response = self.default_error_message

        if is_function_call and response is None:
            response = early_return
        if kwargs.get('force_function_call') and state_machine:
            is_function_call = True
            response = self.build_non_llm_function_call(state_machine)

        if not is_function_call:
            is_function_call = self.is_function_call(response=response) if state_machine else False
        if is_function_call and state_machine and response:
            postprocessing_result = self.postprocessing_service.execute_postprocessing(
                state_machine, response, **kwargs
            )

            # Handle postprocessing results
            if postprocessing_result.get('skip_next_stage', False):
                kwargs['skip_next_stage'] = True
                kwargs['target_stage'] = state_machine.skip_to_step
                logger.info("Postprocessing will skip next stage")

        # Process the response
        return self.process_response(
            response, chat_session, chunks, **kwargs
        )

    def analyze_response_for_postprocessing(self, response):
        """Analyze if response needs postprocessing - can be overridden by subclasses"""
        return self.is_function_call(response)

    def get_llm_response(self, **kwargs):
        """Get response from LLM provider"""
        company_bot = kwargs['company_bot']
        system_prompt = kwargs['system_prompt']
        response = None
        message_to_send = self.get_messages_for_llm(**kwargs)

        session_id = kwargs['session_id']
        profile_id = kwargs.get('profile_id')
        channel_name = kwargs['channel_name']
        chat_session = ChatSession.objects.get(session=session_id)
        state_machine = None
        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, step=chat_session.current_step
            )
        except Exception as e:
            logger.error(f"Error getting state machine for tools: {e}")

        tools = None
        has_state_machine_tool_context = (
                state_machine
                and hasattr(state_machine, 'tool_context')
                and state_machine.tool_context
                and state_machine.tool_context.strip()
        )

        has_company_bot_tool_context = (
                company_bot
                and hasattr(company_bot, 'tool_context')
                and company_bot.tool_context
                and company_bot.tool_context.strip()
        )

        if has_state_machine_tool_context or (
                company_bot.bot_type == CompanyBotTypeChoices.SIMPLE and has_company_bot_tool_context
        ):
            tool_context = (
                state_machine.tool_context.strip()
                if has_state_machine_tool_context
                else company_bot.tool_context.strip()
            )

            try:
                import json_repair
                tools = json_repair.repair_json(tool_context, return_objects=True)
                logger.info("Using state machine tool_context")
            except Exception as e:
                logger.error(f"Failed to parse state machine tool_context: {e}")
                tools = None

        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            try:
                response = handle_bedrock_model(
                    system_prompt=system_prompt,
                    messages=message_to_send,
                    model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    company_bot=company_bot,
                    tools=tools
                )
            except Exception as e:
                logger.error(f"Bedrock Error: %s", e)
                response = None

        elif company_bot.provider == LLMProvider.OPENAI:
            openai_tools = tools if tools else self.get_default_tools_config()
            response = handle_openai_model(
                system_prompt=system_prompt,
                messages=message_to_send,
                model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token,
                tools=openai_tools,
                tool_choice='auto',
                is_json_response=False
            )

        return response

    def get_default_tools_config(self):
        """Get default tools configuration - fallback for when no tool_context is available"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_state_information",
                    "description": "Get the information of the state you want to be in.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "state_name": {
                                "type": "string",
                                "description": "Name of the next state provided in the context."
                            }
                        },
                        "required": ["state_name"]
                    }
                }
            }
        ]

    def get_tools_config(self):
        """Deprecated - use get_default_tools_config() or PromptBuilder.get_tools_from_state_machine()"""
        logger.info("get_tools_config() is deprecated, use get_default_tools_config() instead")
        return self.get_default_tools_config()

    def is_function_call(self, response):
        """Check if response is a function call"""
        if isinstance(response, dict):
            # Check for various function call formats

            # Format 1: Direct tool use format (OLD)
            # {'toolUseId': '...', 'name': 'get_state_information', 'input': {...}}
            if 'toolUseId' in response and 'name' in response:
                return response.get('name') == 'get_state_information'

            # Format 2: Simple function call format (NEW)
            # {'name': 'get_state_information', 'parameters': {...}}
            elif 'name' in response and 'parameters' in response:
                return response.get('name') == 'get_state_information'

            # Format 3: OpenAI function_call format
            # {'function_call': {'name': 'get_state_information', 'arguments': {...}}}
            elif 'function_call' in response:
                function_call = response.get('function_call', {})
                return function_call.get('name') == 'get_state_information'

            # Format 4: OpenAI tool_calls format
            # {'tool_calls': [{'function': {'name': 'get_state_information', ...}}]}
            elif 'tool_calls' in response:
                tool_calls = response.get('tool_calls', [])
                for tool_call in tool_calls:
                    if 'function' in tool_call:
                        function = tool_call.get('function', {})
                        if function.get('name') == 'get_state_information':
                            return True
                return False

            # Format 5: Bedrock response format
            # {'output': {'message': {'content': [{'toolUse': {'name': 'get_state_information', ...}}]}}}
            elif 'output' in response and 'message' in response.get('output', {}):
                content = response['output']['message'].get('content', [])
                for item in content:
                    if 'toolUse' in item:
                        tool_use = item.get('toolUse', {})
                        if tool_use.get('name') == 'get_state_information':
                            return True
                return False

            # Format 6: Just 'parameters' or 'input' without 'name' - check carefully
            elif 'parameters' in response or 'input' in response:
                # If it only has parameters/input but no clear function call indicators,
                # check if the nested data contains function call info
                nested_data = response.get('parameters') or response.get('input')
                if isinstance(nested_data, dict):
                    # Function calls have 'next_state_name' - this is the key differentiator
                    if 'next_state_name' in nested_data:
                        return True
                    # Regular responses have 'response' key - this indicates it's not a function call
                    elif 'response' in nested_data:
                        return False
                    # If neither, fall back to string search
                    else:
                        return 'get_state_information' in str(nested_data)
                # Check if 'get_state_information' appears in the nested data
                return 'get_state_information' in str(nested_data)

            # Format 7: Check if 'get_state_information' appears anywhere in the dict values
            # But be more restrictive - only if it appears as a function name, not in text
            elif any(key in response for key in ['toolUseId', 'tool_calls', 'function_call']):
                return 'get_state_information' in str(response)

            # If none of the above, it's likely a regular dict response (like {"response": "...", "reason": "..."})
            return False

        elif isinstance(response, str):
            return 'get_state_information' in response

        return False

    def save_message(self, session_id, profile_id, message, chunks,
                     status, translated_message, stage=None, other_params=None):
        """Save message to database"""
        save_in_company_db(
            session_id=session_id,
            profile_id=profile_id,
            initiated_by='AI',
            message=message,
            chunks=chunks,
            status=status,
            translated_message=translated_message,
            stage=stage,
            other_params=other_params
        )

    def translate_message(self, message, channel_name, step_number, language, company_bot, extra_content=None):
        """Translate and send message"""
        return translate_and_send_message(
            accumulated_message=message,
            current_channel_name=channel_name,
            current_step_number=step_number,
            finish_reason="stop",
            route=language,
            company_bot=company_bot,
            extra_content=extra_content
        )

    def get_chat_status(self, state_machine, company_bot):
        """Determine chat status based on state"""
        last_state = CompanyStateMachine.objects.filter(company_bot=company_bot).order_by('step').last()
        max_step = last_state.step if last_state else None

        if state_machine.step == max_step:
            return ChatStatus.COMPLETED
        else:
            return ChatStatus.IN_PROGRESS
        # return ChatStatus.COMPLETED if state_machine.name == "APPRECIATION" else ChatStatus.IN_PROGRESS

    # Abstract methods to be implemented by specific bot handlers
    @abstractmethod
    def check_early_return(self, chat_session, **kwargs):
        """Check if we should return early (bot-specific logic)"""
        pass

    @abstractmethod
    def get_messages_for_llm(self, **kwargs):
        """Get appropriate messages for LLM"""
        pass

    @abstractmethod
    def process_response(self, response, chat_session, chunks, **kwargs):
        """Process the LLM response (bot-specific logic)"""
        pass
