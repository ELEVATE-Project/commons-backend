from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from chatbot.llm_models.llm_script import handle_openai_response_api
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.models import ChatStatus, Profile, CompanyBot, CompanyChat
from chatbot.utils.chat_utils import get_guided_chat
import logging
import json

channel_layer = get_channel_layer()
logger = logging.getLogger('django')


class FreeFlowService:
    """
    Service for handling free-flow streaming responses.
    """
    
    def process_and_stream(self, channel_name, session_id, profile_id, route, bot_route):
        """
        Process user message and stream LLM response back via channel layer.
        """
        try:
            logger.info(f"Processing free-flow for session {session_id}, channel {channel_name}")
            
            # 1. Fetch data from database (sync is OK in Celery)
            profile = None
            if profile_id:
                profile = Profile.objects.filter(id=profile_id).first()
            
            # Get company bot configuration
            if profile:
                company_bot = CompanyBot.objects.filter(company=profile.company, route=bot_route).first()
            else:
                company_bot = CompanyBot.objects.filter(route=bot_route).first()
            
            if not company_bot:
                logger.error(f"Company bot not found for route: {bot_route}")
                self._send_error(channel_name, "Bot configuration not found")
                return
            
            # Get conversation history
            all_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
            company_chats = list(all_chats)
            
            logger.info(f"Fetched {len(company_chats)} chat messages for history")
            
            # 2. Format messages for OpenAI using get_guided_chat
            messages = get_guided_chat(
                company_bot=company_bot,
                company_chats=company_chats,
                intro=None  # No intro for free-flow
            )
            
            # 3. Prepare system prompt
            system_prompt = company_bot.context
            
            # Convert to list format for Responses API
            system_prompt = [{'role': 'system', 'content': system_prompt}]
            
            # 4. Parse tools from company_bot.tool_context
            tools = None
            if company_bot.tool_context:
                try:
                    tools = json.loads(company_bot.tool_context)
                    logger.info(f"Loaded tools from company_bot.tool_context: {len(tools) if isinstance(tools, list) else 'object'}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Error parsing company_bot.tool_context: {e}")
            
            # 5. Stream response from OpenAI Responses API
            accumulated_response = ""
            finish_reason = None

            stream = company_bot.stream if hasattr(company_bot, 'stream') else True
            
            logger.info(f"Starting LLM {'streaming' if stream else 'call'} for session {session_id}")
            
            # Call LLM synchronously (this is fine in Celery worker)
            for chunk_data in handle_openai_response_api(
                messages=messages,
                system_prompt=system_prompt,
                max_token=company_bot.max_token if company_bot.max_token else 2048,
                temperature=company_bot.bot_temperature if company_bot.bot_temperature is not None else 0.0,
                company_bot=company_bot,
                top_p=company_bot.filter_score if company_bot.filter_score else None,
                tool_choice="auto",
                tools=tools,
                stream=stream
            ):
                content = chunk_data.get('content', '')
                finish_reason = chunk_data.get('finish_reason')
                error = chunk_data.get('error')
                extra_content = chunk_data.get('extra_content')
                
                if error:
                    logger.error(f'Streaming error: {error}')
                    self._send_error(channel_name, "Error processing your request")
                    return
                
                if content:
                    accumulated_response += content
                
                # Send chunk via channel layer to WebSocket (even if content is empty but finish_reason exists)
                if content or finish_reason:
                    self._send_chunk(channel_name, content, finish_reason, extra_content)
                
                if finish_reason:
                    logger.info(f"Streaming completed with finish_reason: {finish_reason}")
                    break
            
            # 6. Save complete response to database
            if accumulated_response:
                save_in_company_db(
                    session_id=session_id,
                    profile_id=profile_id,
                    initiated_by='AI',
                    message=accumulated_response,
                    chunks=None,
                    status=ChatStatus.IN_PROGRESS,
                    stage= None
                )
                
                logger.info(f'Completed streaming response, length: {len(accumulated_response)} chars')
            else:
                logger.info(f'No response accumulated for session {session_id}')
                
        except Exception as e:
            logger.error(f'Error in process_and_stream: {e}', exc_info=True)
            self._send_error(channel_name, "An error occurred processing your message")
    
    def _send_chunk(self, channel_name, content, finish_reason, extra_content=None):
        """
        Send a chunk via channel layer to the WebSocket.
        """
        try:
            message_data = {
                "type": "chat.message",  # → calls chat_message() in consumer
                "text": {
                    "msg": content,
                    "source": "bot",
                    "type": "chunk",
                    "finish_reason": finish_reason
                },
            }
            
            # Add extra_content (like citations) if present
            if extra_content:
                message_data["text"]["extra_content"] = extra_content
            
            async_to_sync(channel_layer.send)(
                channel_name,
                message_data,
            )
        except Exception as e:
            # Don't crash if WebSocket disconnected - log and continue
            logger.info(f"Failed to send chunk to channel {channel_name}: {e}")
    
    def _send_error(self, channel_name, error_msg):
        """
        Send error message via channel layer to the WebSocket.
        """
        try:
            async_to_sync(channel_layer.send)(
                channel_name,
                {
                    "type": "chat.message",
                    "text": {
                        "msg": error_msg,
                        "source": "bot",
                        "type": "error",
                        "finish_reason": "error"
                    },
                },
            )
        except Exception as e:
            logger.error(f"Failed to send error to channel {channel_name}: {e}")
