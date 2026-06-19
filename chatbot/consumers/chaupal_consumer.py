import json
import traceback
from asgiref.sync import async_to_sync  # Ensure asgiref is installed
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.consumers.base_consumer import BaseConsumer
from chatbot.models import ChatStatus, ChatSession, Profile, CompanyBot, Voice, VoiceType, ChatType, CompanyChat
from chatbot.celery_tasks.chaupal_tasks import get_chaupal_response
from chatbot.models.company_models import CompanyStateMachine
from chatbot.utils.audio_provider_utils import text_translate_provider
import logging

logger = logging.getLogger('django')


class ShikshalokamChaupalConsumer(BaseConsumer):
    try:
        session_id = None
        profile_id = None
        route = None
        company_bot = None

        def disconnect(self, code):
            print('Websocket closed')
            chat_session = ChatSession.objects.filter(session=self.session_id)
            if chat_session.exists():
                c = chat_session[0]
            else:
                c = ChatSession(session=self.session_id)
            c.save_title(self.route)
            company_chat_status = self.determine_company_chat_status(
                session_id=self.session_id, profile_id=self.profile_id, is_disconnected=True, route='/'
            )
            print("COMPANY CHAT STATUS: ", company_chat_status)
            self.update_last_chat_status(chat_status=company_chat_status)
            self.close()

        def receive(self, text_data):
            print(text_data)
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', None)

            try:
                if message_type == 'authenticate':
                    self.session_id = text_data_json.get('sessionid')
                    self.profile_id = text_data_json.get('profileid')
                    self.route = text_data_json.get('route')
                    profile = Profile.objects.filter(id=self.profile_id).first()
                    print(f"Authenticated with session_id: {self.session_id}, profile_id: {self.profile_id}, "
                          f"route: {self.route}")
                    if profile:
                        self.company_bot = CompanyBot.objects.get(company=profile.company, route='/shikshalokam_chaupal')
                    else:
                        self.company_bot = CompanyBot.objects.get(route='/shikshalokam_chaupal')
                    # chat session create (session, profile)
                    cs, cs_created = ChatSession.objects.get_or_create(
                        session=self.session_id,
                        defaults={
                            'profile': profile,
                            'current_step': 1,
                            'company_bot': self.company_bot,
                            'session_status': ChatStatus.IN_PROGRESS,
                            'session_type': ChatType.shikshaChaupal
                        }
                    )
                    print(cs, cs_created)
                else:
                    company_chat_status = self.determine_company_chat_status(
                        session_id=self.session_id, profile_id=self.profile_id, route='/shikshalokam_chaupal'
                    )
                    print("COMPANY CHAT STATUS: ", company_chat_status)
                    async_to_sync(self.channel_layer.send)(
                        self.channel_name,
                        {
                            "type": "chat_message",
                            "text": {"msg": text_data_json["text"], "source": "user"},
                        },
                    )

                if self.route != 'en':
                    print("Company bot: ", self.company_bot)
                    voice_provider = Voice.objects.filter(
                        company_bot=self.company_bot, type=VoiceType.TextToText, language=self.route
                    ).first()
                    if text_data_json and text_data_json.get('text'):
                        existing_chats = CompanyChat.objects.filter(session=self.session_id)
                        chat_session = ChatSession.objects.filter(session=self.session_id).first()
                        state_machine = CompanyStateMachine.objects.get(
                            company_bot=self.company_bot, step=chat_session.current_step
                        )
                        response = text_translate_provider(
                            voice_provider=voice_provider, message_body=text_data_json['text'], target_language='en',
                            source_language=self.route
                        )
                        if response.get('status') == 200:
                            translated_message = response.get('content')
                        else:
                            translated_message = text_data_json['text']
                    else:
                        translated_message=None
                else:
                    translated_message = None

                if message_type != 'authenticate' and text_data_json and text_data_json.get('text'):
                    save_in_company_db(
                        session_id=self.session_id, profile_id=self.profile_id, initiated_by='User',
                        message=text_data_json['text'], chunks=None, status=company_chat_status,
                        translated_message=translated_message, audio_base64=text_data_json.get('asr_audio')
                    )

                print(f"channel_name: {self.channel_name}, session_id: {self.session_id}, profile_id: "
                      f"{self.profile_id}, route: {self.route}")

                if message_type != 'authenticate':
                    get_chaupal_response.delay(
                        self.channel_name, self.session_id, self.profile_id, self.route
                    )
            except Exception as e:
                print(e)
                logger.error('Receive Error: %s', e, exc_info=True)
                traceback.print_exc()

        def connect(self):
            try:
                print('Attempting to connect to websocket')
                super().connect()
            except Exception as e:
                logger.error('Connect Error: %s', e, exc_info=True)
                print(f"Connect Error: {e}")
                traceback.print_exc()
    except Exception as e:
        logger.error('Error: %s', e, exc_info=True)
        print(f"Error: {e}")
