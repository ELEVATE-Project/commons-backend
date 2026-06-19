from abc import ABC, abstractmethod
import logging

from chatbot.models import LLMProvider

logger = logging.getLogger('django')


class BasePreprocessor(ABC):
    """Base class for preprocessing operations"""

    @abstractmethod
    def preprocess(self, state_machine, **kwargs):
        """Execute preprocessing logic"""
        pass


class SimplePreprocessor(BasePreprocessor):
    """Handles simple prompt-based preprocessing"""

    def preprocess(self, state_machine, **kwargs):
        """Execute simple preprocessing using preprocess_prompt"""
        if not state_machine.preprocess_prompt:
            logger.warning(f"No preprocess_prompt defined for state {state_machine.name}")
            return None

        # Get LLM handler
        from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
        from chatbot.models import LLMProvider

        company_bot = kwargs.get('company_bot')
        messages = kwargs.get('messages', [])

        # Build simple prompt
        simple_prompt = self._build_simple_prompt(state_machine.preprocess_prompt, company_bot)

        try:
            if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                response = handle_bedrock_model(
                    system_prompt=simple_prompt,
                    messages=messages,
                    model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    company_bot=company_bot
                )
            elif company_bot.provider == LLMProvider.OPENAI:
                response = handle_openai_model(
                    system_prompt=simple_prompt,
                    messages=messages,
                    model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    tools=None,
                    tool_choice='auto',
                    is_json_response=False
                )
            else:
                response = None

            logger.info(f"Simple preprocessing response for {state_machine.name}: {response}")
            return response

        except Exception as e:
            logger.error(f"Error in simple preprocessing: {e}")
            return None

    def _build_simple_prompt(self, preprocess_prompt, company_bot):
        """Build prompt for simple preprocessing"""
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            return [{'text': preprocess_prompt}]
        else:
            return [{'role': 'system', 'content': preprocess_prompt}]


class ComplexPreprocessor(BasePreprocessor):
    """Handles complex bot-based preprocessing"""

    def preprocess(self, state_machine, **kwargs):
        """Execute complex preprocessing using preprocess_bot"""
        if not state_machine.preprocess_bot:
            logger.warning(f"No preprocess_bot defined for state {state_machine.name}")
            return None

        try:
            # Use the preprocess_bot to generate response like normal flow
            from chatbot.services.core.prompt_builder import PromptBuilder
            from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
            from chatbot.models import LLMProvider

            preprocess_bot = state_machine.preprocess_bot
            messages = kwargs.get('messages', [])

            # Build prompt using the preprocess bot's context
            prompt_builder = PromptBuilder()

            system_prompt = prompt_builder.build_system_prompt(preprocess_bot, None)

            if preprocess_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                response = handle_bedrock_model(
                    system_prompt=system_prompt,
                    messages=messages,
                    model_name=preprocess_bot.llm_model,
                    temperature=preprocess_bot.bot_temperature,
                    max_token=preprocess_bot.max_token,
                    company_bot=preprocess_bot
                )
            elif preprocess_bot.provider == LLMProvider.OPENAI:
                response = handle_openai_model(
                    system_prompt=system_prompt,
                    messages=messages,
                    model_name=preprocess_bot.llm_model,
                    temperature=preprocess_bot.bot_temperature,
                    max_token=preprocess_bot.max_token,
                    tools=None,
                    tool_choice='auto',
                    is_json_response=False
                )
            else:
                response = None

            logger.info(f"Complex preprocessing response for {state_machine.name}: {response}")
            return response

        except Exception as e:
            logger.error(f"Error in complex preprocessing: {e}")
            return None
