import logging
import traceback
from collections import defaultdict
from datetime import timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone

from chatbot.models import CompanyChat, ChatSession
from chatbot.models.company_models import CompanyBot
from chatbot.models.story_models import Story
from chatbot.cron_tasks.telangana_ptm_pilot.kpi_rules import (
    load_keywords,
    classify_sentiment,
    STAGE_CLASSIFIERS,
    CONFIDENCE_THRESHOLD,
)
from chatbot.cron_tasks.telangana_ptm_pilot.kpi_llm import llm_classify_batches

logger = logging.getLogger('django')


def load_sessions_for_metrics() -> list:
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_story = Story.objects.filter(
        session=OuterRef('session'),
        created_at__gte=one_hour_ago,
    )
    already_processed = Story.objects.filter(
        session=OuterRef('session'),
        other_params__kpi_processed=True,
    )
    return list(
        ChatSession.objects
        .filter(session_type='telangana-ptm-pilot')
        .exclude(Exists(recent_story))
        .exclude(Exists(already_processed))
        .values_list('session', flat=True)
    )


def _build_session_chat_map(sessions: list) -> dict:
    chats = (
        CompanyChat.objects
        .filter(session__in=sessions)
        .order_by('created_at')
        .values('session', 'sender_id', 'stage', 'message', 'translated_message')
    )
    result = defaultdict(list)
    for chat in chats:
        result[chat['session']].append(chat)
    return dict(result)


def _effective_text(chat: dict) -> str:
    return chat['translated_message'] or chat['message'] or ''


def _classify_stage_kpis(session_id: str, chats: list, keywords: dict) -> tuple:
    rule_metrics = {}
    llm_queue = []
    stage_texts = {}
    for chat in chats:
        if chat['sender_id'] != 1 and chat['stage'] in STAGE_CLASSIFIERS:
            stage_texts[chat['stage']] = _effective_text(chat)
    for stage, text in stage_texts.items():
        if not text:
            continue
        field_name, classifier_fn = STAGE_CLASSIFIERS[stage]
        label, conf = classifier_fn(text, keywords)
        if label is not None and conf >= CONFIDENCE_THRESHOLD:
            rule_metrics[field_name] = label
        else:
            llm_queue.append((session_id, field_name, text))
    return rule_metrics, llm_queue


def _extract_kpi_for_session(session_id: str, chats: list, keywords: dict) -> tuple:
    """
    Returns (rule_metrics: dict, llm_queue: list of (session_id, field, text))
    """
    rule_metrics = {}
    llm_queue = []

    user_texts = [_effective_text(c) for c in chats if c['sender_id'] != 1]
    transcript = ' '.join(user_texts).strip()
    if transcript:
        label, conf = classify_sentiment(transcript, keywords)
        if label is not None and conf >= CONFIDENCE_THRESHOLD:
            rule_metrics['sentiment'] = label
        else:
            llm_queue.append((session_id, 'sentiment', transcript))

    stage_metrics, stage_llm = _classify_stage_kpis(session_id, chats, keywords)
    rule_metrics.update(stage_metrics)
    llm_queue.extend(stage_llm)

    return rule_metrics, llm_queue


def _save_story_kpi(session_id: str, metrics: dict, error: str = None) -> None:
    story = Story.objects.filter(session=session_id).first()
    if not story:
        logger.info('No Story for session=%s, skipping', session_id)
        return
    params = {**(story.other_params or {}), **metrics, 'kpi_processed': True}
    if error:
        params['kpi_error'] = error
    story.other_params = params
    story.save(update_fields=['other_params', 'updated_at'])


def extract_metrics():
    try:
        company_bot = CompanyBot.objects.get(route='/telangana-ptm-metrics')
    except CompanyBot.DoesNotExist:
        logger.error('CompanyBot with route=/telangana-ptm-metrics not found. Create it in admin first.')
        return

    keywords = load_keywords(company_bot.dynamic_context)

    sessions = load_sessions_for_metrics()
    if not sessions:
        logger.info('No sessions to process for KPI metrics extraction.')
        return

    logger.info('KPI extraction starting — %d sessions to process', len(sessions))
    chat_map = _build_session_chat_map(sessions)

    all_rule_metrics = {}
    all_llm_queue = []
    failed_sessions = {}

    for session_id in sessions:
        try:
            chats = chat_map.get(session_id, [])
            rule_metrics, llm_queue = _extract_kpi_for_session(session_id, chats, keywords)
            all_rule_metrics[str(session_id)] = rule_metrics
            all_llm_queue.extend(llm_queue)
        except Exception:
            err = traceback.format_exc()
            logger.error('Rule extraction failed for session=%s:\n%s', session_id, err)
            failed_sessions[str(session_id)] = err

    sessions_needing_llm = {str(sid) for sid, _, _ in all_llm_queue}

    saved = 0
    for session_id in sessions:
        sid = str(session_id)
        if sid not in sessions_needing_llm:
            _save_story_kpi(sid, dict(all_rule_metrics.get(sid, {})), failed_sessions.get(sid))
            saved += 1

    if all_llm_queue:
        logger.info('Sending %d items to LLM for KPI classification', len(all_llm_queue))
        for batch_sids, batch_result in llm_classify_batches(all_llm_queue, company_bot):
            for sid in batch_sids:
                merged = dict(all_rule_metrics.get(sid, {}))
                for field, value in batch_result.get(sid, {}).items():
                    if field not in merged:
                        merged[field] = value
                if sid not in batch_result and sid not in failed_sessions:
                    failed_sessions[sid] = 'LLM classification returned no results'
                _save_story_kpi(sid, merged, failed_sessions.get(sid))
                saved += 1

    logger.info('KPI extraction complete — %d/%d sessions saved', saved, len(sessions))
