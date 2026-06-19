import csv
import os

from django.db.models import Exists, OuterRef
from django.db.models.functions import Coalesce

from chatbot.models import CompanyChat, ChatSession
from chatbot.models.company_models import CompanyBot
from chatbot.models.story_models import Story
from chatbot.cron_tasks.telangana_ptm_pilot.normalize import load_schools_from_string, Normalizer, UNMATCHED_ROW
from chatbot.cron_tasks.telangana_ptm_pilot.fuzzy_match import FuzzyMatcher, HIGH_CONFIDENCE, LOW_CONFIDENCE
from chatbot.cron_tasks.telangana_ptm_pilot.token_match import TokenMatcher, HIGH_TOKEN_SCORE
from chatbot.cron_tasks.telangana_ptm_pilot.llm_classify import llm_classify, BOT_ROUTE


def load_chats_from_db() -> list[dict]:
    linked_story = Story.objects.filter(session=OuterRef('session'))
    return list(
        CompanyChat.objects
        .filter(
            stage='SCHOOL_NAME',
            receiver_id=1,
            session__in=ChatSession.objects.filter(session_type='telangana-ptm-pilot').values('session'),
        )
        .exclude(Exists(linked_story))
        .annotate(effective_message=Coalesce('translated_message', 'message'))
        .values('id', 'effective_message', 'session', 'created_at', 'updated_at', 'sender_id')
        .order_by('-created_at')
    )


def load_chats_from_csv(path: str) -> list[dict]:
    """Load mock chat data from CSV. Required columns: id, effective_message."""
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [
            {
                'id': int(row['id']),
                'effective_message': row['effective_message'],
                'session': row.get('session'),
                'created_at': row.get('created_at'),
                'updated_at': row.get('updated_at'),
                'sender_id': int(row['sender_id']) if row.get('sender_id') else None,
            }
            for row in reader
        ]


def main(csv_path: str | None = None):
    company_bot = CompanyBot.objects.get(route=BOT_ROUTE)

    print("Loading data...")
    chats = load_chats_from_csv(csv_path) if csv_path else load_chats_from_db()
    schools = load_schools_from_string(company_bot.dynamic_context)
    print(f"  {len(chats)} user responses, {len(schools)} canonical schools")

    normalizer = Normalizer(schools)
    fuzzer = FuzzyMatcher(schools)
    tokener = TokenMatcher(schools)

    results: dict[int, tuple[dict, float, str]] = {}

    # Items that survive each tier: (row_index, message, fuzzy_fallback, fuzzy_score)
    tier3_queue: list[tuple[int, str, dict | None, float]] = []

    # ── Tier 1: exact match  ── Tier 2: fuzzy ≥ 85 ──────────────────────────
    print("\nTier 1 (exact) + Tier 2 (fuzzy ≥85)...")
    for chat in chats:
        i = chat['id']
        msg = str(chat['effective_message'] or "")

        match = normalizer.match(msg)
        if match:
            results[i] = (match, 1.0, "EXACT")
            continue

        match, score, method = fuzzer.match(msg)
        if match and score >= HIGH_CONFIDENCE:
            results[i] = (match, score / 100, method)
        else:
            tier3_queue.append((i, msg, match, score))

    print(f"  EXACT: {sum(1 for _,_,m in results.values() if m=='EXACT')}")
    print(f"  FUZZY_HIGH: {sum(1 for _,_,m in results.values() if m=='FUZZY_HIGH')}")
    print(f"  → {len(tier3_queue)} rows queued for Tier 3")

    # ── Tier 3: TF-IDF token match ───────────────────────────────────────────
    llm_queue: list[tuple[int, str, dict | None, float, list[dict]]] = []

    if tier3_queue:
        print("\nTier 3 (TF-IDF token match)...")
        for i, msg, fuzzy_match, fuzzy_score in tier3_queue:
            token_match, token_score, candidates, token_method = tokener.match(msg)
            if token_match and token_score >= HIGH_TOKEN_SCORE:
                results[i] = (token_match, token_score, "TOKEN_HIGH")
            else:
                # Keep best fuzzy fallback; pass TF-IDF candidates to LLM
                best_fallback = token_match if token_match else fuzzy_match
                best_fallback_score = token_score if token_match else fuzzy_score / 100
                llm_queue.append((i, msg, best_fallback, best_fallback_score, candidates))

        print(f"  TOKEN_HIGH: {sum(1 for _,_,m in results.values() if m=='TOKEN_HIGH')}")
        print(f"  → {len(llm_queue)} rows queued for Tier 4 (LLM)")

    # ── Tier 4: Bedrock Llama 3.3 70B ────────────────────────────────────────
    if llm_queue:
        use_llm = bool(os.environ.get("AWS_PROFILE") or os.environ.get("AWS_ACCESS_KEY_ID"))
        if not use_llm:
            print("\nWARNING: No AWS credentials found (set AWS_PROFILE or AWS_ACCESS_KEY_ID).")
            print("  Falling back to best available match for queued rows.")
        else:
            print("\nTier 4 (Bedrock Converse — Llama 3.3 70B)...")

        llm_inputs = [(msg, candidates) for _, msg, _, _, candidates in llm_queue]
        llm_results = llm_classify(llm_inputs) if use_llm else [None] * len(llm_queue)

        for (i, msg, fallback, fallback_score, _), llm_result in zip(llm_queue, llm_results):
            if llm_result:
                results[i] = (llm_result, 0.9, "LLM")
            elif fallback and fallback_score >= LOW_CONFIDENCE / 100:
                results[i] = (fallback, fallback_score, "FUZZY_LOW")
            else:
                results[i] = (UNMATCHED_ROW, 0.0, "UNMATCHED")

    # ── Save results to Story model ───────────────────────────────────────────
    print(f"\nSaving {len(results)} results to Story model...")
    chat_meta = {chat['id']: chat for chat in chats}
    saved = 0
    for chat_id, (school, score, method) in results.items():
        chat = chat_meta.get(chat_id, {})
        Story.objects.update_or_create(
            session=chat.get('session') or str(chat_id),
            defaults={
                'title': 'Telangana School Classification',
                'author_id': chat.get('sender_id'),
                'other_params': {
                    'school': school,
                    'score': score,
                    'method': method,
                    'message': chat.get('effective_message', ''),
                },
            },
        )
        saved += 1
    print(f"  Saved {saved} Story records.")