from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from chatbot.models import LLMModel
from chatbot.models.enums import LLMProvider
from chatbot.utils.llm import LLM
from typing import Optional, List, Dict
from django.core.validators import URLValidator
from openai import OpenAI
from pprint import pprint
from retrying import retry
from chatbot.models import LLMModel, Company
import boto3
import json
import json_repair
import logging
import os
import requests
import traceback


logger = logging.getLogger('django')
validate = URLValidator()
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER'))


def handle_llama_model(
        messages, max_token, model_name=None, is_json_format=True, temperature=None, top_p=None, seed=None, n=None,
        stream=False, url_to_use=None
):

    if url_to_use:
        url = url_to_use
    else:
        url = os.getenv('LLAMA_BASE_URL') + 'v1/chat/completions'
        # finetune_url = os.getenv('LLAMAFINETUNE_BASE_URL') + 'v1/chat/completions'

    payload = {
        "messages": messages,
        "max_tokens": max_token,
    }

    if model_name:
        payload["model"] = model_name
    else:
        payload["model"] = LLMModel.LLAMA_3_1_8B_OPS

    if is_json_format:
        payload["response_format"] = {"type": "json_object"}
    if seed is not None:
        payload["seed"] = seed
    if n is not None:
        payload["n"] = n
    if top_p is not None:
        payload["top_p"] = top_p
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(payload),
        stream=stream
    )
    print(response.content)
    response_str = str(response.content, encoding="utf-8")

    if is_json_format:
        response_json = json.loads(response_str)
        response_content = response_json['choices'][0]['message']['content']
        response_content = response_content.replace('\n', '').replace('\t', '').replace(
            '\r', '').replace('\\n', '').replace('\\t', '').replace('\\r', '')
        print("BEFORE LOADS: ", response_content)
        response_json = json.loads(response_content)
        return response_json
    else:
        return response_str


def handle_openai_model(
        messages, max_token=None, temperature=None, company_bot=None, model_name=None, is_json_response=True,
        stream=False, key_name='OPENAI_API_KEY', is_actual_key=False, tools=None, tool_choice=None, client_choice=None,
        top_p=None, system_prompt=None
):
    try:
        if is_actual_key:
            client_api_key = key_name
        else:
            client_api_key = os.getenv(key_name)

        if not client_api_key:
            raise ValueError(f"No API key found for '{key_name}'. Please set the environment variable correctly.")

        if client_choice:
            client = client_choice
        else:
            client = OpenAI(api_key=client_api_key)

        if model_name:
            model_to_use = model_name
        elif company_bot:
            model_to_use = company_bot.llm_model
        else:
            model_to_use = LLMModel.GPT4_O_MINI

        if system_prompt and isinstance(system_prompt, list):
            messages = system_prompt+messages

        request_data = {
            "model": model_to_use,
            "messages": messages,
        }
        token_limit_models = {
            LLMModel.GPT5_MINI,
            LLMModel.GPT5_2_PRO,
            LLMModel.GPT5_2,
        }
        if max_token:
            if company_bot.llm_model in token_limit_models:
                request_data["max_completion_tokens"] = max_token
            else:
                request_data["max_tokens"]= max_token
        if temperature:
            request_data['temperature']= temperature
        if is_json_response:
            request_data["response_format"] = {"type": "json_object"}
        if stream:
            request_data["stream"] = stream
        if tools:
            request_data["tools"]= tools
            if tool_choice:
                request_data["tool_choice"]= tool_choice
        if top_p is not None and company_bot.llm_model not in token_limit_models:
            request_data['top_p'] = top_p
        print("request_data: ", request_data)
        response = client.chat.completions.create(**request_data)
        price = calculate_and_log_llm_cost(
            response=response, model_id=model_to_use, company_bot=company_bot
        )
        print("raw res: ", response)
        if is_json_response:
            response_content = response.choices[0].message.content
            response_json = None
            if response_content:
                response_json = json.loads(response_content)
            return response_json
        elif tools:
            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and len(tool_calls) > 0:
                return {}
            return response.choices[0].message.content if response.choices else response
        else:
            return response.choices[0].message.content if response.choices else response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise

def get_pricing_from_company_bot(company_bot, model_id):
    try:
        # Determine if company_bot is dict-like or an object (model instance)
        if isinstance(company_bot, dict):
            other_params = company_bot.get('other_params')
        else:
            # Model instance, has attribute
            other_params = getattr(company_bot, 'other_params', None)

        if not other_params:
            return None

        # Parse other_params if it is a string
        if isinstance(other_params, str):
            other_params_parsed = json.loads(other_params)
        else:
            other_params_parsed = other_params

        # Check if pricing data exists
        pricing_data = other_params_parsed.get('model_pricing')
        if not pricing_data:
            logger.info(f"❌ No pricing_data key found in company bot other params.")
            return None

        logger.info(f"🔍 Searching for model_id: '{model_id}'")
        logger.info(f"🔍 Available pricing keys: {list(pricing_data.keys())}")

        # Get pricing for current model
        model_pricing = pricing_data.get(model_id)
        if not model_pricing:
            logger.info(f"❌ No exact match found for: '{model_id}'")
            model_pricing = pricing_data.get('llama3-3-70b')

        if model_pricing and 'input_cost_per_1k' in model_pricing and 'output_cost_per_1k' in model_pricing:
            return {
                'input': float(model_pricing['input_cost_per_1k']),
                'output': float(model_pricing['output_cost_per_1k'])
            }

        return None

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing pricing from company_bot.other_params: {e}")
        return None

def retry_if_result_none(result):
    return result is None

@retry(stop_max_attempt_number=llm_retry_number, retry_on_result=retry_if_result_none, wrap_exception=True)
def handle_bedrock_model(
        company_bot, system_prompt=None, messages=None, max_token=None, temperature=None, top_p=None,
        model_name=None, region_name='us-west-2', tools=None, is_json_response=False, aws_key=None,
        aws_secret_key=None, stop_sequences=None
):
    # Support company_bot as either dict or model instance
    if isinstance(company_bot, dict):
        connect_timeout = company_bot.get('connect_timeout', 5.0)
        read_timeout = company_bot.get('read_timeout', 10.0)
        chat_history_limit = company_bot.get('chat_history_limit', 1000)
    else:
        connect_timeout = getattr(company_bot, 'connect_timeout', 5.0)
        read_timeout = getattr(company_bot, 'read_timeout', 10.0)
        chat_history_limit = getattr(company_bot, 'chat_history_limit', 1000)

    boto_config = BotoConfig(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"mode": "adaptive"}
    )

    bedrock_runtime = boto3.client(
        service_name='bedrock-runtime',
        region_name=region_name,
        aws_access_key_id=aws_key if aws_key else AWS_KEY,
        aws_secret_access_key=aws_secret_key if aws_secret_key else AWS_SECRET_KEY,
        config=boto_config
    )
    print("aws_key used: ", aws_key if aws_key else AWS_KEY)
    if model_name:
        model_id = model_name
    else:
        model_id = 'meta.llama3-1-8b-instruct-v1:0'

    inference_config = {}
    additional_model_fields = {}

    if max_token:
        inference_config['maxTokens'] = max_token
    if temperature is not None:
        inference_config['temperature'] = temperature
    if top_p:
        inference_config['topP'] = top_p
    if stop_sequences:
        inference_config['stopSequences'] = stop_sequences
    # Remove trailing assistant message
    if messages and messages[-1]['role'] == 'assistant':
        messages.pop()
    # Enforce chat history rules
    if messages:
        # Find last user message
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]['role'] == 'user':
                last_user_idx = i
                break

        if last_user_idx is None:
            messages = []
        else:
            start_idx = max(0, last_user_idx - chat_history_limit)

            # Ensure first message is always a user
            if messages[start_idx]['role'] != 'user':
                for j in range(start_idx + 1, last_user_idx + 1):
                    if messages[j]['role'] == 'user':
                        start_idx = j
                        break

            messages = messages[start_idx:last_user_idx + 1]

    try:
        request_payload = {
            'modelId': model_id,
            'messages': messages,
            'system': system_prompt,
        }
        if inference_config:
            request_payload['inferenceConfig'] = inference_config
        if tools:
            print("tools: ", tools)
            request_payload['toolConfig'] = tools.get('toolConfig')

        logger.info('Bedrock request payload: %s', request_payload)
        response = bedrock_runtime.converse(**request_payload)

        logger.info('Conversation Bedrock response: %s', json.dumps(response))
        print('Conversation Bedrock response: ', response)

        usage_metrics = response.get('usage', {})
        if usage_metrics:
            logger.info("--------------USAGE METRICS-------------")
            input_tokens = usage_metrics.get('inputTokens', 0)
            output_tokens = usage_metrics.get('outputTokens', 0)
            total_tokens = usage_metrics.get('totalTokens', 0)
            logger.info(f'💰 Token Usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}')
            print(f'💰 Token Usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}')

            pricing = get_pricing_from_company_bot(
                company_bot=company_bot, model_id=model_id
            )
            if pricing:
                input_cost = (input_tokens / 1000) * pricing['input']
                output_cost = (output_tokens / 1000) * pricing['output']
                total_cost = input_cost + output_cost

                logger.info(
                    f'💵 Model Cost - Input: ${input_cost:.6f} (${pricing["input"]}/1K), Output: ${output_cost:.6f} '
                    f'(${pricing["output"]}/1K), Total: ${total_cost:.6f}')
                print(
                    f'💵 Model Cost - Input: ${input_cost:.6f} (${pricing["input"]}/1K), Output: ${output_cost:.6f} '
                    f'(${pricing["output"]}/1K), Total: ${total_cost:.6f}')
            else:
                logger.info('💵 No pricing data configured in company_bot.other_params')
                print('💵 No pricing data configured in company_bot.other_params')

            # Log additional metrics if available
            if 'stopReason' in response.get('stopReason', ''):
                stop_reason = response.get('stopReason')
                logger.info(f'🛑 Stop Reason: {stop_reason}')
                print(f'🛑 Stop Reason: {stop_reason}')
        else:
            logger.info('⚠️ No usage metrics found in response')
            print('⚠️ No usage metrics found in response')

        content_arr = response['output']['message']['content']
        content = content_arr[0]
        content_tool = content.get('toolUse')
        if content_tool:
            if isinstance(content_tool, str):
                final_output = json_repair.repair_json(content_tool, return_objects=True)
            else:
                final_output = content_tool
        else:
            content_text = content.get('text')
            json_start = content_text.find('{')
            if json_start != -1:
                json_str = content_text[json_start:]
                json_str = json_str.replace('\n', '').replace('\r', '').strip()
                while json_str and (json_str.endswith("'") or json_str.endswith('"') or json_str.endswith(',')):
                    json_str = json_str[:-1].strip()
                try:
                    final_output = json_repair.repair_json(json_str, return_objects=True)
                    logger.info('Loads final_output: %s', final_output)
                except json.JSONDecodeError as e:
                    return None
            elif is_json_response:
                return None
            else:
                return content_text

        return final_output
    except ClientError as e:
        error_response = e.response
        logger.error("❌ Bedrock ClientError:")
        logger.error(f"Error Code: {error_response['Error']['Code']}")
        logger.error(f"Error Message: {error_response['Error']['Message']}")
        logger.error(f"Request ID: {error_response.get('ResponseMetadata', {}).get('RequestId')}")
        print("❌ ClientError:")
        print("Error Code:", error_response["Error"]["Code"])
        print("Error Message:", error_response["Error"]["Message"])
        print("Request ID:", error_response.get("ResponseMetadata", {}).get("RequestId"))
    except Exception as e:
        logger.error('Error processing request: %s', e, exc_info=True)
        print(f'❌ Error processing Bedrock request: {e}')
        return None


def get_file_metadata_from_vector_store(client, vector_store_ids, file_id):
    """
    Fetch file metadata (attributes) from vector store.
    Returns attributes dict or None if not found.
    """
    if not vector_store_ids:
        return None
    
    try:
        # Try each vector store until we find the file
        for vs_id in vector_store_ids:
            try:
                # Retrieve the vector store file object
                vs_file = client.vector_stores.files.retrieve(
                    vector_store_id=vs_id,
                    file_id=file_id
                )
                
                # Check if attributes exist
                if hasattr(vs_file, 'attributes') and vs_file.attributes:
                    logger.info(f"Found metadata for file {file_id} in vector store {vs_id}")
                    return vs_file.attributes
                    
            except Exception as e:
                # File not in this vector store, try next
                logger.error(f"File {file_id} not found in vector store {vs_id}: {e}")
                continue
        
        logger.info(f"No metadata found for file {file_id} in any vector store")
        return None
        
    except Exception as e:
        logger.error(f"Error fetching file metadata for {file_id}: {e}")
        return None


def add_source_with_organization(source_entry, metadata):
    """
    Adds 'url' and conditionally adds 'organization' if company exists in DB.
    """
    if not metadata:
        metadata = {}
    # Add URL if present in metadata
    if metadata and 'url' in metadata:
        source_entry['url'] = metadata['url']
    
    # Check for company slug in metadata
    company_slug = metadata.get('company', 'shikshalokamstaging')
    if company_slug:
        try:
            # Fetch company from database
            company = Company.objects.filter(slug=company_slug).first()
            if company:
                source_entry['organization'] = {
                    'name': company.name,
                    'slug': company.slug
                }
                logger.info(f"Added organization info for company: {company.name}")
            else:
                logger.info(f"Company with slug '{company_slug}' not found in database")
        except Exception as e:
            logger.error(f"Error fetching company with slug '{company_slug}': {e}")
    
    return source_entry


def calculate_and_log_llm_cost(*, response, model_id, company_bot=None, provider="openai"):
    """
    Generic cost calculator for OpenAI-style responses.
    Supports:
    - Chat Completions API
    - Responses API
    - Streaming + non-streaming
    """

    if not response or not company_bot:
        return None

    usage = getattr(response, "usage", None)
    if not usage:
        logger.info("⚠️ LLM response has no usage data")
        return None

    # --- Normalize token fields across APIs ---
    input_tokens = (
        getattr(usage, "input_tokens", None)       # Responses API
        or getattr(usage, "prompt_tokens", 0)      # Chat Completions
    )

    output_tokens = (
        getattr(usage, "output_tokens", None)      # Responses API
        or getattr(usage, "completion_tokens", 0)  # Chat Completions
    )

    total_tokens = (
        getattr(usage, "total_tokens", None)
        or (input_tokens + output_tokens)
    )

    logger.info(
        f"💰 {provider.upper()} Tokens — "
        f"Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}"
    )
    print(
        f"💰 {provider.upper()} Tokens — "
        f"Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}"
    )

    pricing = get_pricing_from_company_bot(
        company_bot=company_bot,
        model_id=model_id
    )

    if not pricing:
        logger.info(f"💵 No pricing configured for {provider} model: {model_id}")
        print(f"💵 No pricing configured for {provider} model: {model_id}")
        return None

    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    total_cost = input_cost + output_cost

    logger.info(
        f"💵 {provider.upper()} Cost — "
        f"Input: ${input_cost:.6f}, "
        f"Output: ${output_cost:.6f}, "
        f"Total: ${total_cost:.6f}"
    )
    print(
        f"💵 {provider.upper()} Cost — "
        f"Input: ${input_cost:.6f}, "
        f"Output: ${output_cost:.6f}, "
        f"Total: ${total_cost:.6f}"
    )

    return {
        "provider": provider,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
    }


def calculate_and_log_openai_cost(*, response, model_id, company_bot=None):
    """
    Calculates and logs OpenAI cost using Responses API usage.
    Works for both streaming and non-streaming responses.
    """

    if not response or not company_bot:
        return None

    usage = getattr(response, "usage", None)
    if not usage:
        logger.info("⚠️ OpenAI response has no usage data")
        return None

    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens or 0
    total_tokens = usage.total_tokens or (input_tokens + output_tokens)

    logger.info(
        f"💰 OpenAI Tokens — Input: {input_tokens}, "
        f"Output: {output_tokens}, Total: {total_tokens}"
    )
    print(
        f"💰 OpenAI Tokens — Input: {input_tokens}, "
        f"Output: {output_tokens}, Total: {total_tokens}"
    )

    pricing = get_pricing_from_company_bot(
        company_bot=company_bot,
        model_id=model_id
    )

    if not pricing:
        logger.info(f"💵 No pricing configured for OpenAI model: {model_id}")
        print(f"💵 No pricing configured for OpenAI model: {model_id}")
        return None

    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    total_cost = input_cost + output_cost

    logger.info(
        f"💵 OpenAI Cost — Input: ${input_cost:.6f}, Output: ${output_cost:.6f}, Total: ${total_cost:.6f}"
    )

    print(
        f"💵 OpenAI Cost — Input: ${input_cost:.6f}, Output: ${output_cost:.6f}, Total: ${total_cost:.6f}"
    )

    return {
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
    }


def handle_openai_response_api(
        messages, system_prompt=None, max_token=None, temperature=None, company_bot=None,
        model_name=None, key_name='OPENAI_API_KEY', is_actual_key=False,
        top_p=None, tool_choice="auto", tools: Optional[List[Dict]] = None, stream=False,
        is_json_response=False
):
    """
    OpenAI Responses API with file_search and function calling support.

    This uses the new Responses API (client.responses.create) which supports:
    - file_search tool with vector stores
    - Function calling (e.g., for file downloads)
    - Streaming and non-streaming responses
    - Unified interface for chat + tools
    """
    if is_actual_key:
        client_api_key = key_name
    else:
        client_api_key = os.getenv(key_name)

    if not client_api_key:
        yield {
            'error': f"No API key found for '{key_name}'. Please set the environment variable correctly.",
            'finish_reason': 'error'
        }
        return

    client = OpenAI(api_key=client_api_key)

    if model_name:
        model_to_use = model_name
    elif company_bot:
        model_to_use = company_bot.llm_model
    else:
        model_to_use = LLMModel.GPT4_O_MINI

    # Build input array for Responses API (includes system + conversation messages)
    input_messages = []

    # Add system prompt as first message
    if system_prompt:
        if isinstance(system_prompt, list):
            # Extract system content from list format
            for msg in system_prompt:
                if msg.get('role') == 'system':
                    input_messages.append({
                        'role': 'system',
                        'content': msg.get('content', '')
                    })
        elif isinstance(system_prompt, str):
            input_messages.append({
                'role': 'system',
                'content': system_prompt
            })

    # Enforce chat history rules (similar to bedrock)
    if messages and company_bot and hasattr(company_bot, 'chat_history_limit') and company_bot.chat_history_limit:
        # Remove trailing assistant message
        if messages[-1]['role'] == 'assistant':
            messages = messages[:-1]

        # Find last user message
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]['role'] == 'user':
                last_user_idx = i
                break

        if last_user_idx is None:
            messages = []
        else:
            start_idx = max(0, last_user_idx - company_bot.chat_history_limit)

            # Ensure first message is always a user
            if messages[start_idx]['role'] != 'user':
                for j in range(start_idx + 1, last_user_idx + 1):
                    if messages[j]['role'] == 'user':
                        start_idx = j
                        break

            messages = messages[start_idx:last_user_idx + 1]

    # Add conversation messages
    input_messages.extend(messages)

    # Build request data for Responses API
    # Note: client.responses.stream() doesn't take 'stream' parameter - it streams by default
    request_data = {
        "model": model_to_use,
        "input": input_messages
    }

    if max_token:
        request_data["max_output_tokens"] = max_token
    if temperature is not None:
        request_data['temperature'] = temperature
    if top_p:
        request_data['top_p'] = top_p
    if is_json_response:
        request_data["response_format"] = {"type": "json_object"}


    # Add tools to request if provided (already parsed by caller)
    if tools:
        request_data["tools"] = tools
        request_data["tool_choice"] = tool_choice
        logger.info(f"Using tools configuration: {len(tools) if isinstance(tools, list) else 'single tool'}")
    else:
        logger.info("⚠️ No tools provided")

    logger.info("Responses API %s request: %s", "streaming" if stream else "non-streaming", request_data)

    # Extract vector_store_ids from tools for metadata fetching
    vector_store_ids = []
    if tools:
        for tool in (tools if isinstance(tools, list) else [tools]):
            if tool.get('type') == 'file_search' and tool.get('vector_store_ids'):
                vector_store_ids.extend(tool.get('vector_store_ids'))

    try:
        if stream:
            # Use Responses API with streaming context manager
            sources = []
            seen_file_ids = set()
            function_call_name = None
            function_call_args = ""
            function_call_id = None
            function_call_complete = False
            
            with client.responses.stream(**request_data) as response_stream:
                for event in response_stream:
                    logger.info(f"OpenAI Event: {event.type} | Data: {event}")

                    # Handle function call delta events (streaming function arguments character-by-character)
                    if event.type == 'response.function_call_arguments.delta':
                        # Accumulate function arguments using snapshot (complete JSON so far)
                        function_call_args = event.snapshot
                        if not function_call_id:
                            function_call_id = event.item_id
                        logger.info(f"Function call delta: snapshot length = {len(function_call_args)} chars")
                        print(f"📝 Function args snapshot: {function_call_args[:100]}...")
                    
                    # Handle function call done event
                    elif event.type == 'response.function_call_arguments.done':
                        function_call_complete = True
                        logger.info(f"Function call arguments complete: {len(function_call_args)} chars")
                        print(f"✅ Function call arguments COMPLETE")
                        
                        # Yield function call response with sources
                        # This will be processed by common_handler to extract content and send to user
                        yield {
                            'function_call': {
                                'name': function_call_name,
                                'arguments': function_call_args  # JSON string with filename and content
                            },
                            'finish_reason': 'function_call',  # Internal marker for common_handler
                            'extra_content': {
                                'sources': sources  # Include sources collected from annotations
                            }
                        }
                    
                    # Handle function call output item to get function name
                    elif event.type == 'response.output_item.added' and hasattr(event, 'item'):
                        if hasattr(event.item, 'type') and event.item.type == 'function_call':
                            function_call_name = event.item.name
                            function_call_id = event.item.id
                            logger.info(f"Function call detected: {function_call_name}")
                            print(f"🎯 Function name: {function_call_name}")
                    
                    # Handle file citation annotations
                    if event.type == 'response.output_text.annotation.added' and event.annotation[
                        "type"] == 'file_citation':
                        file_id = event.annotation["file_id"]
                        if file_id not in seen_file_ids:
                            source_entry = {
                                "source_id": file_id,
                                "title": event.annotation["filename"]
                            }

                            # Fetch metadata from vector store
                            metadata = get_file_metadata_from_vector_store(client, vector_store_ids, file_id)

                            # Enrich source with organization info
                            source_entry = add_source_with_organization(source_entry, metadata)

                            sources.append(source_entry)
                            seen_file_ids.add(file_id)

                    # Handle ResponseTextDeltaEvent - extract incremental delta
                    elif event.type == 'response.output_text.delta':
                        content_chunk = event.delta or ""
                        yield {
                            'content': content_chunk,
                            'finish_reason': None
                        }

                    # Handle ResponseTextDoneEvent - text output completed
                    elif event.type == 'response.output_text.done':
                        yield {
                            'content': '',
                            'finish_reason': 'stop',
                            'extra_content': {
                                "sources": sources
                            }
                        }

                    # Handle ResponseCompletedEvent - full response finished
                    elif event.type == 'response.completed':
                        logger.info(f"Response completed")
                        price = calculate_and_log_openai_cost(
                            response=event.response, model_id=model_to_use, company_bot=company_bot
                        )
                        break

                    # Handle error events
                    elif event.type == 'error':
                        error_msg = getattr(event, 'error', {}).get('message', 'Unknown error')
                        logger.error(f"Stream error: {error_msg}")
                        yield {
                            'content': '',
                            'error': error_msg,
                            'finish_reason': 'error'
                        }
                        break
        else:
            # Non-streaming mode - get complete response at once
            response = client.responses.create(**request_data)
            print("Openai response: ", response)
            logger.info(f"Openai response: {response}")

            price = calculate_and_log_openai_cost(
                response=response, model_id=model_to_use, company_bot=company_bot
            )

            logger.info(f"free-flows response: {response}")
            logger.info("Non-streaming response received")
            # Extract full text from response
            # The response.output is a list that may contain:
            # - ResponseFileSearchToolCall (tool calls)
            # - ResponseOutputMessage (actual text messages)
            full_text = ""
            sources = []
            seen_file_ids = set()
            
            if hasattr(response, 'output') and response.output:
                for output_item in response.output:
                    # Check if this is a ResponseOutputMessage (has 'content' attribute)
                    if hasattr(output_item, 'content') and output_item.content:
                        # The content is a list of ResponseOutputText objects
                        for content_item in output_item.content:
                            if hasattr(content_item, 'text'):
                                full_text += content_item.text

                            # Extract sources from annotations (deduplicate by file_id)
                            if hasattr(content_item, 'annotations') and content_item.annotations:
                                for annotation in content_item.annotations:
                                    if annotation.type == 'file_citation' and annotation.file_id not in seen_file_ids:
                                        source_entry = {
                                            "source_id": annotation.file_id,
                                            "title": annotation.filename
                                        }
                                        # Fetch metadata from vector store
                                        metadata = get_file_metadata_from_vector_store(client, vector_store_ids,
                                                                                       annotation.file_id)

                                        # Enrich source with organization info
                                        source_entry = add_source_with_organization(source_entry, metadata)
                                        sources.append(source_entry)
                                        seen_file_ids.add(annotation.file_id)
            
            logger.info(f"Extracted text length: {len(full_text)} chars, unique sources: {len(sources)}")
            
            # Yield single complete response
            yield {
                'content': full_text,
                'finish_reason': 'stop',
                'extra_content': {
                    "sources": sources
                }
            }
    except Exception as e:
        error_msg = f"Error during Responses API {'streaming' if stream else 'call'}: {str(e)}"
        logger.error('Error: %s', e, exc_info=True)
        print(error_msg)
        yield {
            'content': '',
            'error': error_msg,
            'finish_reason': 'error'
        }


def handle_bedrock_invoke_model(
        messages=None, max_token=None, temperature=None, top_p=None,
        model_name=None, region_name='us-west-2', tools=None
):

    if model_name:
        model_id = model_name
    else:
        model_id = 'meta.llama3-1-8b-instruct-v1:0'

    print("USING MODEL ID: ", model_id)

    print("Messages: ", messages)
    try:

        body = json.dumps({
            "prompt": json.dumps(messages),
            "max_gen_len": max_token,
            "temperature": temperature,
            "top_p": top_p
        })

        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=region_name,
            aws_access_key_id=AWS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )

        response = bedrock_runtime.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )

        a = response.get('body').read()
        b = a.decode('utf-8')
        response_body = json.loads(b)
        print(response_body)
        print(type(response_body))

        result = response_body.get('generation', '')
        print("\nResult:\n\t", result)


        return result

    except Exception as e:
        print(f"Error processing request: {e}")
