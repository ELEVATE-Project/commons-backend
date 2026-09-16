import json
import os
import traceback
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.consumers.async_base_consumer import AsyncBaseConsumer
from chatbot.models import ChatStatus, ChatSession, Profile, CompanyBot
import logging
from channels.db import database_sync_to_async
import jwt
from chatbot.celery_tasks.free_flow_tasks import get_free_flow_response

logger = logging.getLogger('django')


class FreeFlowConsumer(AsyncBaseConsumer):
    """
    WebSocket consumer for free-flow conversation.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.profile_id = None
        self.route = None
        self.bot_route = None
        self.company_bot = None
        self.flow_name = None
        self.ip_address = None
        self.access_token = None

    async def disconnect(self, code):
        try:
            logger.info(f"Free-flow websocket closed with code: %s", code)
        except Exception as e:
            logger.error('Disconnect Error: %s', e, exc_info=True)
        finally:
            await super().disconnect(code)

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', None)
            company_chat_status = None
            
            if message_type == 'authenticate':
                # Handle authentication
                self.session_id = text_data_json.get('sessionid')
                self.profile_id = text_data_json.get('profileid')
                self.route = text_data_json.get('route', 'en')
                self.bot_route = text_data_json.get('bot_route')
                self.flow_name = text_data_json.get('flow_name', 'free_flow')
                self.ip_address = text_data_json.get('address')
                self.access_token = text_data_json.get('access_token')

                profile = await self.get_profile(self.profile_id)
                logger.info(
                    f"Free-flow channel_name: %s, session_id: %s, profile_id: %s, route: %s",
                    self.channel_name, self.session_id, self.profile_id, self.route
                )

                user_id = await self.handle_access_token(self.access_token)

                # If an access_token was provided but verification failed, reject authentication
                if self.access_token and not user_id:
                    logger.error(
                        "Authentication failed: invalid access_token for channel %s session %s",
                        self.channel_name, self.session_id
                    )
                    await self.send(text_data=json.dumps({
                        "text": {
                            "msg": "Authentication failed: invalid access token",
                            "source": "system",
                            "type": "auth_error"
                        }
                    }))
                    return
                self.company_bot = await self.get_company_bot(profile, self.bot_route)

                # Create chat session asynchronously
                await self.create_chat_session(
                    self.session_id, profile, self.company_bot, self.ip_address, user_id
                )
                
            else:
                # Handle regular chat messages
                user_message = text_data_json.get('text')
                if not user_message:
                    logger.info("Received empty message")
                    return
                
                # Determine chat status
                company_chat_status = await self.determine_company_chat_status_async(
                    session_id=self.session_id, profile_id=self.profile_id, route=self.bot_route
                )
                
                # Echo user message back
                await self.send(text_data=json.dumps({
                    "text": {
                        "msg": user_message,
                        "source": "user"
                    }
                }))
                
                # Save user message to database
                await database_sync_to_async(save_in_company_db)(
                    session_id=self.session_id,
                    profile_id=self.profile_id,
                    initiated_by='User',
                    message=user_message,
                    chunks=None,
                    status=company_chat_status,
                    translated_message=None,
                    audio_base64=text_data_json.get('asr_audio')
                )
                
                logger.info(
                    f"Processing free-flow message - channel_name: %s, session_id: %s",
                    self.channel_name, self.session_id
                )
                
                # Launch Celery task for streaming (FIRE AND FORGET)
                get_free_flow_response.delay(
                    self.channel_name,
                    self.session_id,
                    self.profile_id,
                    self.route,
                    self.bot_route
                )

        except Exception as e:
            logger.error('Receive Error: %s', e, exc_info=True)
            await self.send(text_data=json.dumps({
                "text": {
                    "msg": "An error occurred processing your message",
                    "source": "system",
                    "type": "error"
                }
            }))

    async def connect(self):
        try:
            logger.info(f"Attempting to connect to free-flow websocket")
            await super().connect()
        except Exception as e:
            logger.error('Connect Error: %s', e, exc_info=True)



    @database_sync_to_async
    def get_profile(self, profile_id):
        if not profile_id:
            return None
        return Profile.objects.filter(id=profile_id).first()

    @database_sync_to_async
    def handle_access_token(self, access_token):
        user_id = None
        try:
            if access_token:
                # Verify with signature using RS256 when access_token is provided
                PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")

                decoded = jwt.decode(
                    access_token,
                    PUBLIC_KEY,
                    algorithms=["HS256"]
                )
                logger.info("Decoded JWT: %s", decoded)

                if decoded:
                    user_id = decoded.get('data', {}).get('id')
        
        except jwt.ExpiredSignatureError:
            logger.error('Access token has expired', exc_info=True)
        except jwt.InvalidTokenError as e:
            logger.error('Invalid access token: %s', e, exc_info=True)
        except Exception as e:
            logger.error('Access token Decode Error: %s', e, exc_info=True)

        logger.info("User_id: %s", user_id)
        return user_id

    @database_sync_to_async
    def get_company_bot(self, profile, route):
        if profile:
            return CompanyBot.objects.get(company=profile.company, route=route)
        else:
            return CompanyBot.objects.get(route=route)

    @database_sync_to_async
    def create_chat_session(self, session_id, profile, company_bot, ip_address, user_id):
        cs, cs_created = ChatSession.objects.get_or_create(
            session=session_id,
            defaults={
                'profile': profile,
                'current_step': 1,  # Not used in free-flow but required
                'language': self.route,
                'company_bot': company_bot,
                'session_status': ChatStatus.IN_PROGRESS,
                'user_id': user_id,
                'session_type': self.flow_name
            }
        )
        logger.info(f"Chat session for free-flow: %s %s", cs, cs_created)

        if not cs_created:
            if cs.language != self.route:
                cs.language = self.route

            other_params = cs.other_params or {}
            other_params["ip_address"] = ip_address
            cs.other_params = other_params
            cs.save(update_fields=["language", "other_params"])
        else:
            cs.other_params = {"ip_address": ip_address}
            cs.save(update_fields=["other_params"])

        return cs


