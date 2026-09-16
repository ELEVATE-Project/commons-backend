import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import json_repair
except ImportError:
    class _JsonRepairFallback:
        @staticmethod
        def repair_json(value, return_objects=True):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return value
            return value

    json_repair = _JsonRepairFallback()

try:
    CURRENT_FILE = Path(__file__).resolve()
except NameError:
    CURRENT_FILE = Path.cwd()
PROJECT_ROOT = None
for parent in CURRENT_FILE.parents:
    if (parent / "manage.py").exists():
        PROJECT_ROOT = parent
        break

if PROJECT_ROOT is not None:
    project_root_str = str(PROJECT_ROOT)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shikshalokam_mohini.settings")

import django

django.setup()

from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import CompanyBot, CompanyChat, LLMProvider, Story, StoryTranslation
from chatbot.utils.chat_utils import get_guided_chat

logger = logging.getLogger("django")

DEFAULT_STAGE_NAME = "CHALLENGES"
DEFAULT_BOT_ROUTE = "/fix-challenges-bot"
DEFAULT_MAX_WORKERS = 4


def _load_json_file(file_path: str) -> Any:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_session_ids(input_json_file: str) -> List[str]:
    """Load session IDs from JSON."""
    data = _load_json_file(input_json_file)

    session_ids: List[str] = []
    if isinstance(data, list):
        session_ids = [str(item).strip() for item in data if str(item).strip()]
    elif isinstance(data, dict):
        raw = data.get("session_ids", [])
        if isinstance(raw, list):
            session_ids = [str(item).strip() for item in raw if str(item).strip()]

    # Preserve order and de-duplicate
    seen = set()
    unique_ids = []
    for session_id in session_ids:
        if session_id not in seen:
            seen.add(session_id)
            unique_ids.append(session_id)

    return unique_ids


def _try_parse_json(response: Any) -> Any:
    if isinstance(response, str):
        try:
            return json_repair.repair_json(response, return_objects=True)
        except Exception:
            return response
    return response


def unwrap_llm_response(response: Any) -> Any:
    """Unwrap tool-call wrappers and nested {type: object, value: ...} structures."""
    response = _try_parse_json(response)

    if isinstance(response, dict):
        extracted = response.get("parameters") or response.get("input")
        if isinstance(extracted, dict):
            response = extracted

    def _unwrap(obj: Any) -> Any:
        if isinstance(obj, dict):
            while obj.get("type") == "object" and "value" in obj:
                obj = obj.get("value") or {}
            return {k: _unwrap(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_unwrap(item) for item in obj]
        return obj

    return _unwrap(response)


def normalize_challenges_faced(value: Any) -> Optional[List[str]]:
    """Coerce challenges_faced to a clean list of strings."""
    if isinstance(value, str):
        try:
            parsed = json_repair.repair_json(value, return_objects=True)
        except Exception:
            parsed = value
        if isinstance(parsed, list):
            value = parsed
        else:
            return None

    if not isinstance(value, list):
        return None

    result = []
    for item in value:
        if isinstance(item, str):
            item = item.replace('\\"', '"').replace("\\'", "'").strip()
        result.append(item)

    return result or None


def extract_challenges_faced_from_response(response: Any) -> Optional[Any]:
    """Extract challenges_faced from bot response exactly as returned by mitigation bot."""
    cleaned = unwrap_llm_response(response)

    if isinstance(cleaned, dict):
        challenges_faced = cleaned.get("challenges_faced")
        if challenges_faced is not None:
            return normalize_challenges_faced(challenges_faced)

    return None


def get_mitigation_bot(route: str = DEFAULT_BOT_ROUTE) -> CompanyBot:
    bot = CompanyBot.objects.filter(route=route).first()
    if not bot:
        raise ValueError(f"CompanyBot with route '{route}' not found")
    return bot


def resolve_bedrock_tools(tool_context: Any) -> Optional[Dict[str, Any]]:
    """Resolve the inner Bedrock toolConfig from a bot tool_context payload."""
    if not tool_context:
        return None

    if isinstance(tool_context, str):
        try:
            tool_context = json_repair.repair_json(tool_context, return_objects=True)
        except Exception:
            return None

    if isinstance(tool_context, dict):
        if tool_context.get("toolConfig"):
            return tool_context

        for key in ("content_tool", "story_tool", "tool"):
            candidate = tool_context.get(key)
            if isinstance(candidate, dict) and candidate.get("toolConfig"):
                return candidate

        for value in tool_context.values():
            if isinstance(value, dict) and value.get("toolConfig"):
                return value

    if isinstance(tool_context, list) and tool_context:
        for item in tool_context:
            if isinstance(item, dict) and item.get("toolConfig"):
                return item

    return None


def get_challenges_stage_chats(
    session_id: str,
    stage_name: str = DEFAULT_STAGE_NAME,
) -> List[CompanyChat]:
    """Return all chats for the requested stage in chronological order."""
    chats = list(CompanyChat.objects.filter(session=session_id).order_by("created_at"))
    if not chats:
        return []

    return [c for c in chats if c.stage == stage_name]


def call_temporary_mitigation_bot(
    mitigation_bot: CompanyBot,
    relevant_chats: List[CompanyChat],
) -> Any:
    """Call mitigation bot with the provided chat slice."""
    messages = get_guided_chat(company_bot=mitigation_bot, company_chats=relevant_chats)

    if mitigation_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        tools = resolve_bedrock_tools(mitigation_bot.tool_context)

        system_prompt = [{"text": mitigation_bot.context}] if mitigation_bot.context else None

        return handle_bedrock_model(
            system_prompt=system_prompt,
            messages=messages,
            model_name=mitigation_bot.llm_model,
            temperature=mitigation_bot.bot_temperature,
            max_token=mitigation_bot.max_token,
            company_bot=mitigation_bot,
            tools=tools,
        )

    if mitigation_bot.provider == LLMProvider.OPENAI:
        system_prompt = [
            {
                "role": "system",
                "content": mitigation_bot.context or "",
            }
        ]
        return handle_openai_model(
            system_prompt=system_prompt,
            messages=messages,
            model_name=mitigation_bot.llm_model,
            temperature=mitigation_bot.bot_temperature,
            max_token=mitigation_bot.max_token,
            is_json_response=True,
        )

    raise ValueError(f"Unsupported provider for mitigation bot: {mitigation_bot.provider}")


def update_story_and_translations(
    story: Story,
    challenges_faced: Any,
    dry_run: bool = True,
) -> Tuple[bool, bool]:
    """Update story.other_params and all translations. Returns (story_updated, translations_updated)."""
    story_updated = False
    translations_updated = False

    other_params = story.other_params if isinstance(story.other_params, dict) else {}
    current = other_params.get("challenges_faced")

    if current != challenges_faced:
        other_params["challenges_faced"] = challenges_faced
        story.other_params = other_params
        story_updated = True
        if not dry_run:
            story.save(update_fields=["other_params"])

    translations = StoryTranslation.objects.filter(story=story)
    for tr in translations:
        tr_other_params = tr.other_params if isinstance(tr.other_params, dict) else {}
        if tr_other_params.get("challenges_faced") != challenges_faced:
            tr_other_params["challenges_faced"] = challenges_faced
            tr.other_params = tr_other_params
            translations_updated = True
            if not dry_run:
                tr.save(update_fields=["other_params"])

    return story_updated, translations_updated


def process_single_session(
    session_id: str,
    mitigation_bot: CompanyBot,
    stage_name: str = DEFAULT_STAGE_NAME,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Process one session and update challenges_faced for guest-discussion story only."""
    result = {
        "session": session_id,
        "status": "skipped",
        "reason": "",
        "story_id": None,
        "challenges_faced": None,
        "story_updated": False,
        "translations_updated": False,
    }

    try:
        story = Story.objects.filter(session=session_id).first()
        if not story:
            result["reason"] = "story_not_found"
            return result

        result["story_id"] = story.id

        other_params = story.other_params if isinstance(story.other_params, dict) else {}
        if other_params.get("flow") != "guest-discussion":
            result["reason"] = "not_guest_discussion"
            return result

        relevant_chats = get_challenges_stage_chats(
            session_id=session_id,
            stage_name=stage_name,
        )
        if not relevant_chats:
            result["reason"] = "no_relevant_chats"
            return result

        llm_response = call_temporary_mitigation_bot(
            mitigation_bot=mitigation_bot,
            relevant_chats=relevant_chats,
        )

        new_challenges_faced = extract_challenges_faced_from_response(llm_response)
        if not new_challenges_faced:
            result["reason"] = "challenges_faced_not_found_in_bot_response"
            return result

        story_updated, translations_updated = update_story_and_translations(
            story=story,
            challenges_faced=new_challenges_faced,
            dry_run=dry_run,
        )

        result["challenges_faced"] = new_challenges_faced
        result["story_updated"] = story_updated
        result["translations_updated"] = translations_updated
        result["status"] = "updated" if (story_updated or translations_updated) else "no_change"
        return result

    except Exception as e:
        logger.exception("Error while processing session %s", session_id)
        result["status"] = "failed"
        result["reason"] = str(e)
        return result


def process_sessions_from_json(
    input_json_file: str,
    dry_run: bool = True,
    bot_route: str = DEFAULT_BOT_ROUTE,
    stage_name: str = DEFAULT_STAGE_NAME,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Dict[str, Any]:
    """Main entrypoint."""
    if not os.path.exists(input_json_file):
        raise FileNotFoundError(f"Input JSON file not found: {input_json_file}")

    session_ids = load_session_ids(input_json_file)
    if not session_ids:
        return {
            "dry_run": dry_run,
            "total_sessions": 0,
            "updated": 0,
            "no_change": 0,
            "skipped": 0,
            "failed": 0,
            "results": [],
        }

    mitigation_bot = get_mitigation_bot(route=bot_route)
    max_workers = max(1, int(max_workers or 1))

    results: List[Dict[str, Any]] = []
    summary = {
        "dry_run": dry_run,
        "total_sessions": len(session_ids),
        "updated": 0,
        "no_change": 0,
        "skipped": 0,
        "failed": 0,
        "results": results,
    }

    logger.info(
        "Starting challenges_faced mitigation for %s sessions. dry_run=%s",
        len(session_ids),
        dry_run,
    )

    def run_one(idx_and_session: Tuple[int, str]) -> Tuple[int, Dict[str, Any]]:
        idx, session_id = idx_and_session
        row = process_single_session(
            session_id=session_id,
            mitigation_bot=mitigation_bot,
            stage_name=stage_name,
            dry_run=dry_run,
        )
        return idx, row

    indexed_results: List[Tuple[int, Dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_one, (idx, session_id))
            for idx, session_id in enumerate(session_ids)
        ]

        for future in as_completed(futures):
            idx, row = future.result()
            indexed_results.append((idx, row))

            if row["status"] == "updated":
                summary["updated"] += 1
            elif row["status"] == "no_change":
                summary["no_change"] += 1
            elif row["status"] == "failed":
                summary["failed"] += 1
            else:
                summary["skipped"] += 1

    for _, row in sorted(indexed_results, key=lambda item: item[0]):
        results.append(row)

    logger.info(
        "Mitigation completed. total=%s updated=%s no_change=%s skipped=%s failed=%s dry_run=%s",
        summary["total_sessions"],
        summary["updated"],
        summary["no_change"],
        summary["skipped"],
        summary["failed"],
        summary["dry_run"],
    )

    return summary


def _setup_django() -> None:
    """Bootstrap Django so this script can be executed directly from terminal."""
    try:
        current = Path(__file__).resolve()
    except NameError:
        current = Path.cwd()
    project_root = None

    for parent in current.parents:
        if (parent / "manage.py").exists():
            project_root = parent
            break

    if project_root is None:
        raise RuntimeError("Could not locate project root containing manage.py")

    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shikshalokam_mohini.settings")

    import django

    django.setup()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mitigate challenges_faced for guest-discussion stories using /fix-challenges-bot."
    )
    parser.add_argument(
        "--input-json",
        required=True,
        help="Path to input JSON containing session IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving to DB.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to DB (overrides --dry-run).",
    )
    parser.add_argument(
        "--bot-route",
        default=DEFAULT_BOT_ROUTE,
        help="Mitigation bot route. Default: /fix-challenges-bot",
    )
    parser.add_argument(
        "--stage-name",
        default=DEFAULT_STAGE_NAME,
        help="Stage name for challenges context. Default: CHALLENGES",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="ThreadPoolExecutor worker count. Default: 4",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _setup_django()
    args = _parse_args()
    dry_run = False if args.apply else True
    if args.dry_run:
        dry_run = True

    summary = process_sessions_from_json(
        input_json_file=args.input_json,
        dry_run=dry_run,
        bot_route=args.bot_route,
        stage_name=args.stage_name,
        max_workers=args.max_workers,
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
