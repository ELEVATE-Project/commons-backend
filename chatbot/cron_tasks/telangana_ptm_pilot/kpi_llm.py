import json
import logging
import traceback

from chatbot.llm_models.llm_script import handle_bedrock_model

logger = logging.getLogger('django')

BOT_ROUTE = '/telangana-ptm-metrics'
LLM_BATCH_SIZE = 25


def _build_messages(batch: list) -> list:
    payload = [{'id': s, 'field': f, 'text': t} for s, f, t in batch]
    return [
        {'role': 'user', 'content': [{'text': json.dumps(payload)}]},
    ]


def _parse_response(response) -> dict:
    try:
        results = response.get('results', [])
        return {str(item['id']): {item['field']: {k: v for k, v in item.items() if k not in ('id', 'field')}}
                for item in results if 'id' in item and 'field' in item}
    except Exception:
        logger.warning('Failed to parse LLM response: %s', response)
        return {}


def llm_classify_batches(items: list, company_bot):
    """
    items: list of (session_id, field, text)
    Yields (batch_session_ids: set[str], result: {session_id: {field: label_dict}}) per batch.
    """
    for i in range(0, len(items), LLM_BATCH_SIZE):
        batch = items[i:i + LLM_BATCH_SIZE]
        batch_session_ids = {str(sid) for sid, _, _ in batch}
        messages = _build_messages(batch)
        try:
            response = handle_bedrock_model(
                company_bot=company_bot,
                system_prompt=[{'text': company_bot.context}],
                messages=messages,
                model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token,
            )
            parsed = _parse_response(response)
        except Exception:
            logger.error('LLM batch %d-%d failed:\n%s', i, i + LLM_BATCH_SIZE, traceback.format_exc())
            parsed = {}
        yield batch_session_ids, parsed
