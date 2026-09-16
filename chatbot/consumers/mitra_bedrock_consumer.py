import json
import os
import traceback
from django.conf import settings
from asgiref.sync import async_to_sync
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.consumers.base_consumer import BaseConsumer
from chatbot.models import ChatStatus, ChatSession, Profile, CompanyBot, Voice, VoiceType, ChatType
import jwt
from chatbot.celery_tasks.mitra_bedrock_tasks import get_mitra_bedrock_response
from chatbot.utils.audio_provider_utils import text_translate_provider
import logging


logger = logging.getLogger('django')
PUBLIC_KEY = os.getenv('JWT_PUBLIC_KEY')

class MitraBedrockConsumer(BaseConsumer):
    try:
        session_id = None
        profile_id = None
        access_token = None
        route = None

        def disconnect(self, code):
            print('Websocket closed')
            logger.info('Websocket closed')
            chat_session = ChatSession.objects.filter(session=self.session_id)
            if chat_session.exists():
                c = chat_session[0]
            else:
                c = ChatSession(session=self.session_id)
            c.save_title(self.route)
            company_chat_status = self.determine_company_chat_status(
                session_id=self.session_id, profile_id=self.profile_id, is_disconnected=True, route='/mitra-create'
            )
            print("COMPANY CHAT STATUS: ", company_chat_status)
            self.update_last_chat_status(chat_status=company_chat_status)
            self.close()

        def receive(self, text_data):
            print(text_data)
            logger.info('Received text_data: %s', text_data)
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', None)

            try:
                if message_type == 'authenticate':
                    self.session_id = text_data_json.get('sessionid')
                    self.profile_id = text_data_json.get('profileid')
                    self.access_token = text_data_json.get('access_token')
                    self.route = text_data_json.get('route')
                    profile = Profile.objects.filter(id=self.profile_id).first()
                    print(f"Authenticated with session_id: {self.session_id}, profile_id: {self.profile_id}, "
                          f"route: {self.route}")
                    logger.info("Authenticated with session_id: %s, profile_id: %s, route: %s",
                                self.session_id, self.profile_id, self.route)
                    print(f"Received access_token: {self.access_token}")
                    user_id = None 
                    if self.access_token:
                        try:
                            decoded = jwt.decode(
                                self.access_token,
                                PUBLIC_KEY,
                                algorithms=["HS256"]
                            )
                            user_id = decoded.get('data', {}).get('id')
                        except jwt.ExpiredSignatureError:
                            logger.error("JWT token expired")
                            user_id = None
                        except jwt.InvalidTokenError:
                            logger.error("Invalid JWT token")
                            user_id = None

                    print("User_id: ", user_id)
                    logger.info("User_id: %s", user_id)

                    # chat session create (session, profile)
                    cs, cs_created = ChatSession.objects.get_or_create(
                        session=self.session_id,
                        defaults={
                            'profile': profile,
                            'current_step': 1,
                            'language': self.route,
                            'company_bot': CompanyBot.objects.get(route='/mitra-create'),
                            'session_status': ChatStatus.IN_PROGRESS,
                            'user_id': user_id,
                            'session_type': ChatType.creation
                        }
                    )
                    print(cs, cs_created)
                    if not cs_created and cs.language != self.route:
                        cs.language = self.route
                        cs.save(update_fields=['language'])
                else:
                    company_chat_status = self.determine_company_chat_status(
                        session_id=self.session_id, profile_id=self.profile_id, route='/mitra-create'
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
                        company_bot = CompanyBot.objects.filter(route='/mitra-create').first()
                        voice_provider = Voice.objects.filter(
                            company_bot=company_bot, type=VoiceType.TextToText, language=self.route
                        ).first()

                        response = text_translate_provider(
                            voice_provider=voice_provider, message_body=text_data_json['text'], target_language='en',
                            source_language=self.route
                        )
                        if response.get('status') == 200:
                            translated_message = response.get('content')
                        else:
                            translated_message = text_data_json['text']
                    else:
                        translated_message = None
                    save_in_company_db(self.session_id, self.profile_id, 'User', text_data_json['text'],
                                       None, company_chat_status, translated_message)

                    print(f"channel_name: {self.channel_name}, session_id: {self.session_id}, profile_id: {self.profile_id}, "
                          f"route: {self.route}")
                    logger.info("channel_name: %s, session_id: %s, profile_id: %s, route: %s",
                                self.channel_name, self.session_id, self.profile_id, self.route)

                    self.route = self.route.strip()

                    get_mitra_bedrock_response.delay(
                        self.channel_name, self.session_id, self.profile_id, self.route
                    )
            except Exception as e:
                print(e)
                logger.error('Receive Error: %s', e, exc_info=True)
                traceback.print_exc()

        def connect(self):
            try:
                print('Attempting to connect to websocket')
                logger.info('Attempting to connect to websocket')
                super().connect()
            except Exception:
                logger.error('Connect Error: %s', e, exc_info=True)
                traceback.print_exc()
    except Exception as e:
        logger.error('Error: %s', e, exc_info=True)
        print(f"Error: {e}")
