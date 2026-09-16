import traceback

from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models.company_models import CompanyBot

BOT_ROUTE = '/classify-school-telangana-ptm'


def _build_candidate_block(candidates: list[dict]) -> str:
    lines = [
        f"{s['district']} | {s['mandal']} | {s['school_name']} | {s['udise_code']}"
        for s in candidates
    ]
    return "\n".join(lines)


def _build_user_prompt(message: str, candidates: list[dict]) -> str:
    candidate_block = _build_candidate_block(candidates)
    return (
        f"Parent's response: {message or ''}\n\n"
        f"Candidate schools (DISTRICT | MANDAL | SCHOOL_NAME | UDISE_CODE):\n"
        f"{candidate_block}"
    )


def _parse_bedrock_result(result) -> dict | None:
    if not isinstance(result, dict):
        return None
    if result.get("result") == "UNMATCHED":
        return None
    if all(k in result for k in ("district", "mandal", "school_name", "udise_code")):
        return {
            "district": str(result["district"]).strip().upper(),
            "mandal": str(result["mandal"]).strip().upper(),
            "school_name": str(result["school_name"]).strip(),
            "udise_code": str(result["udise_code"]).strip(),
        }
    return None


def _call_llm(
    idx: int,
    message: str,
    candidates: list[dict],
    company_bot: CompanyBot,
) -> tuple[int, dict | None]:
    system_prompt = [{'text': company_bot.context}]
    messages = [{'role': 'user', 'content': [{'text': _build_user_prompt(message, candidates)}]}]
    try:
        result = handle_bedrock_model(
            company_bot=company_bot,
            system_prompt=system_prompt,
            messages=messages,
            model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature,
            max_token=company_bot.max_token,
        )
        return idx, _parse_bedrock_result(result)
    except Exception as e:
        traceback.print_exc()
        print(f"  [row {idx}] Bedrock error: {e}")
        return idx, None


def llm_classify(
    items: list[tuple[str, list[dict]]],  # (message, candidates)
) -> list[dict | None]:
    """
    Classify via Bedrock Converse. Config (model, temperature, system prompt) from CompanyBot.
    Each request only receives the top-K TF-IDF candidates, not the full school list.
    """
    if not items:
        return []

    company_bot = CompanyBot.objects.get(route=BOT_ROUTE)

    results: dict[int, dict | None] = {}
    total = len(items)

    for idx, (msg, candidates) in enumerate(items):
        if not candidates:
            results[idx] = None
            continue
        _, result = _call_llm(idx, msg, candidates, company_bot)
        results[idx] = result
        done = idx + 1
        if done % 50 == 0 or done == total:
            print(f"  LLM progress: {done}/{total}")

    return [results.get(i) for i in range(len(items))]
