from django.db import models
from chatbot.models import CompanyChat, Profile, CompanyBot, ChatStatus, LLMModel, Voice, VoiceType, LLMProvider, \
    ChatType, StoryLanguageChoices
from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.utils.audio_provider_utils import text_translate_provider
import json_repair

from chatbot.utils.chat_utils import get_guided_chat


class ChatSession(models.Model):
    """
    Represents an active chat session between a user profile and a company bot.
    Stores session metadata, conversation state, and handles title generation using LLMs.
    """

    session = models.CharField(max_length=255, unique=True)
    profile = models.ForeignKey(Profile, on_delete=models.DO_NOTHING, null=True, blank=True)
    company_bot = models.ForeignKey(CompanyBot, on_delete=models.SET_NULL, null=True, blank=True)
    language = models.CharField(max_length=1000, choices=StoryLanguageChoices.choices,
                                default=StoryLanguageChoices.ENGLISH)
    title = models.CharField(max_length=255, null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    current_step = models.IntegerField(null=True, blank=True)
    session_context = models.JSONField(null=True, blank=True)
    session_status = models.CharField(max_length=20, choices=ChatStatus.choices, null=True, blank=True)
    project_id = models.CharField(max_length=400, null=True, blank=True)
    user_id = models.CharField(max_length=400, null=True, blank=True)
    session_type = models.CharField(max_length=255, null=True, blank=True)
    other_params = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save_title(self, language='en'):
        company_chats = CompanyChat.objects.select_related('sender', 'receiver').filter(session=self.session).order_by('created_at').values("receiver", "receiver__id", "translated_message", "message", "status", "created_at")
        if self.profile:
            company_bot = CompanyBot.objects.filter(company=self.profile.company, route='/mohini_title').first()
        else:
            company_bot = CompanyBot.objects.filter(route='/mohini_title').first()

        if not company_bot:
            return

        messages = get_guided_chat(
            company_bot=company_bot, company_chats=company_chats
        )
        prompt = self._get_prompt(company_bot=company_bot)

        json_output = self._handle_llm_model(
            prompt=prompt, messages=messages, company_bot=company_bot
        )
        try:
            if isinstance(json_output, str):
                json_output = json_repair.repair_json(json_output, return_objects=True)
            output_title = json_output.get('title')
        except Exception as e:
            print("Error: ", e)
            output_title = 'MI Story'
        if language != 'en':
            voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.TextToText, language=language
            ).first()

            response = text_translate_provider(
                voice_provider=voice_provider, message_body=output_title, target_language=language,
                source_language='en'
            )
            if response.get('status') == 200:
                output_title = response.get('content')

        self.title = output_title
        self.save()

    def _get_prompt(self, company_bot):
        prompt = company_bot.context
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            return [{'text': prompt}]
        elif company_bot.provider == LLMProvider.OPENAI:
            return [
                {
                    'role': 'system',
                    'content': prompt
                },
            ]

    def _handle_llm_model(self, prompt, messages, company_bot):
        response_json = None
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            tool = company_bot.tool_context
            if tool and isinstance(tool, str):
                tool = json_repair.repair_json(tool, return_objects=True)
            response_json = handle_bedrock_model(
                system_prompt=prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
                tools=tool, company_bot=company_bot
            )
        elif company_bot.provider == LLMProvider.OPENAI:
            response_json = handle_openai_model(
                system_prompt=prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token
            )

        if response_json and isinstance(response_json, dict):
            if response_json.get('parameters'):
                response_json = response_json.get('parameters')
            elif response_json.get('input'):
                response_json = response_json.get('input')
        return response_json

    def _parse_response(self, response):
        response_str = str(response.content, encoding="utf-8")
        response_json = json_repair.repair_json(response_str, return_objects=True)
        response_content = response_json['choices'][0]['message']['content']
        cleaned_content = (response_content.replace('\n', '').replace('\t', '').replace('\r', '')
                           .replace('\\n', '').replace('\\t', '').replace('\\r', ''))
        return json_repair.repair_json(cleaned_content, return_objects=True)
