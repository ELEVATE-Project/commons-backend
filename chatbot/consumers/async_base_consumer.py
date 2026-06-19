import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from chatbot.models import ChatSession, CompanyChat, ChatStatus, Profile, CompanyBot
from chatbot.models.company_models import CompanyStateMachine
import logging
import traceback

logger = logging.getLogger('django')


class AsyncBaseConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def disconnect(self, code):
        try:
            if hasattr(self, 'session_id') and self.session_id:
                session_id = self.session_id
            else:
                session_id = self.scope.get('cookies', {}).get('sessionid')

            if session_id:
                await self.save_chat_session(session_id)
                if getattr(self, 'profile_id', None) and getattr(self, 'bot_route', None):
                    company_chat_status = await self.determine_company_chat_status_async(
                        session_id=session_id,
                        profile_id=self.profile_id,
                        is_disconnected=True,
                        route=self.bot_route
                    )
                    await self.update_last_chat_status_async(chat_status=company_chat_status)
        except Exception as e:
            traceback.print_exc()
            logger.error('Receive Error: %s', e, exc_info=True)

        finally:
            await self.close()

    async def receive(self, text_data):
        raise NotImplementedError("receive method must be implemented in subclass")

    async def chat_message(self, event):
        text = event["text"]
        await self.send(text_data=json.dumps({"text": text}))

    @database_sync_to_async
    def save_chat_session(self, session_id):
        chat_session = ChatSession.objects.filter(session=session_id)
        if chat_session.exists():
            c = chat_session[0]
        else:
            c = ChatSession(session=session_id)

        if hasattr(self, 'route'):
            c.save_title(self.route)
        else:
            c.save_title()

    @database_sync_to_async
    def determine_company_chat_status(self, session_id, profile_id, route, is_disconnected=False):
        if not session_id:
            return None
        chat_session = ChatSession.objects.filter(session=session_id).first()
        if not chat_session:
            return None

        profile = Profile.objects.filter(id=profile_id).first()
        try:
            if profile:
                company_bot = CompanyBot.objects.get(company=profile.company, route=route)
            else:
                company_bot = CompanyBot.objects.get(route=route)

            state_machine = CompanyStateMachine.objects.filter(
                company_bot=company_bot, step=chat_session.current_step
            ).first()

            existing_chats = CompanyChat.objects.filter(session=session_id)

            if existing_chats.count() == 0:
                return ChatStatus.STARTED
            elif state_machine and state_machine.name != 'APPRECIATION' and is_disconnected:
                return ChatStatus.PAUSED
            elif existing_chats.exists():
                last_chat = existing_chats.last()
                if last_chat.status == ChatStatus.PAUSED:
                    return ChatStatus.RESUME
            elif chat_session and chat_session.session_status == ChatStatus.COMPLETED:
                return ChatStatus.COMPLETED

            return ChatStatus.IN_PROGRESS
        except Exception as e:
            logger.info('Error in determine_company_chat_status: %s', e, exc_info=True)

            return ChatStatus.PAUSED  # Default safe value

    async def determine_company_chat_status_async(self, session_id, profile_id, route, is_disconnected=False):
        return await self.determine_company_chat_status(session_id, profile_id, route, is_disconnected)

    @database_sync_to_async
    def update_last_chat_status(self, chat_status):
        if not hasattr(self, 'session_id') or not self.session_id:
            return

        try:
            existing_chat = CompanyChat.objects.filter(session=self.session_id).last()
            if not existing_chat:
                return

            if existing_chat.status != ChatStatus.COMPLETED:
                existing_chat.status = chat_status
                existing_chat.save()
        except Exception as e:
            logger.info('Error in update_last_chat_status: %s', e, exc_info=True)

    async def update_last_chat_status_async(self, chat_status):
        await self.update_last_chat_status(chat_status)
