import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from tqdm import tqdm
from jinja2 import Template
from chatbot.models import CompanyBot
import json
import os
import json_repair
from retrying import retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from chatbot.utils.llm import LLM
from chatbot.models.enums import LLMProvider
from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.constants.post_processing_constants import CHALLENGE_CATEGORIES

logger = logging.getLogger('django')


# -------------- CONFIG ------------------
INPUT_FILE = 'chatbot/scripts/guest_discussion/post_processing/chaupal_four_challenge.json'
OUTPUT_FILE = 'chatbot/scripts/challenges/llm_unique_challenges_output.json'
SECOND_OUTPUT_FILE = 'chatbot/scripts/challenges/flat_challenges_output.json'
DEFAULT_BATCH_SIZE = 5
DEFAULT_MAX_WORKERS = 2
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', '3'))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# -------------- CORE FUNCTIONS ------------------

def chunk_data(data: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
    """Split list of challenge dicts into batches."""
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def build_user_message(batch: List[Dict[str, Any]], company_bot) -> List[Dict[str, Any]]:
    """Build the user message for the LLM using tag_context from CompanyBot.
    
    Each item in batch is a dict with keys: challenge_text, challenge_count, category.
    """
    challenges_text = "\n".join(
        [f"- [count: {item['challenge_count']}] {item['challenge_text']}" for item in batch]
    )
    
    categories_list = ", ".join(CHALLENGE_CATEGORIES)
    
    # Render the tag_context Jinja2 template with variables
    context_data = {
        "challenges_text": challenges_text,
        "categories_list": categories_list,
    }
    
    template = Template(company_bot.tag_context)
    prompt_text = template.render(context_data)
    
    logger.info(f"[challenges_script] Rendered prompt for batch (first 500 chars): {prompt_text[:500]}")
    
    return [
        {
            'role': 'user',
            'content': [{
                'text': prompt_text
            }]
        }
    ]

def call_llm(batch: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
    """Call LLM for a batch of challenge dicts and return parsed result.
    
    Returns:
        {
            "challenges": List[dict] or None,
            "categories": List[dict] or None
        }
    """
    try:
        company_bot = CompanyBot.objects.filter(route='/challenges_script').first()
        if not company_bot:
            logger.error("[challenges_script] CompanyBot with route '/challenges_script' not found.")
            return {"challenges": None, "categories": None}

        if not company_bot.tag_context:
            logger.error("[challenges_script] tag_context is empty for CompanyBot route='/challenges_script'. Please set the prompt template in admin.")
            return {"challenges": None, "categories": None}

        messages = build_user_message(batch, company_bot)

        tool = company_bot.tool_context
        if tool and isinstance(tool, str):
            tool = json_repair.repair_json(tool, return_objects=True)

        formatted_prompt = [{
            'text': company_bot.context
        }]

        output = handle_bedrock_model(
            system_prompt=formatted_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool
        )
        if output:
            parsed = get_clean_output(response=output)
            return parsed if parsed else {"challenges": None, "categories": None}

        return {"challenges": None, "categories": None}
    except Exception as e:
        print(f"Error in call_llm for batch {index}: {str(e)}")
        return {"challenges": None, "categories": None}


def process_all_batches(
    data: List[Dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    save_to_file: bool = False,
    output_file: str = OUTPUT_FILE
) -> Dict[str, Any]:
    """Process all batches and return results dictionary.    """
    chunks = chunk_data(data, batch_size)
    results = {}

    print(f"🚀 Starting processing of {len(chunks)} batches with {max_workers} workers...")

    def run_one_batch(idx_batch):
        idx, batch = idx_batch
        print(f"[Worker] Running batch {idx}")
        result = call_llm(batch, idx)
        return idx, result

    # Parallel execution
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_one_batch, (i, chunk)) for i, chunk in enumerate(chunks)]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Batches Completed"):
            idx, result = future.result()
            batch_key = f"challenge_{idx}"
            results[batch_key] = {
                "challenges": result.get("challenges"),
                "categories": result.get("categories")
            }

    if save_to_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Saved {len(chunks)} batches to {output_file}")

    return results


# -------------- ENTRY POINT ------------------
def run_unique_challenge_processing(
    start: int = 0,
    end: int = None,
    input_file: str = None,
    input_data: List[Dict[str, Any]] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    save_to_file: bool = False,
    output_file: str = OUTPUT_FILE,
    second_output_file: str = SECOND_OUTPUT_FILE
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run unique challenge processing.
    """
    # Get challenges from input_data or input_file
    if input_data is not None:
        challenges = input_data
    elif input_file:
        with open(input_file, "r") as f:
            raw = json.load(f)
        challenges = _ensure_challenge_dicts(raw)
    else:
        input_file = INPUT_FILE
        with open(input_file, "r") as f:
            raw = json.load(f)
        challenges = _ensure_challenge_dicts(raw)

    total = len(challenges)
    end = end if end is not None else total
    selected_challenges = challenges[start:end]

    print(f"🚀 Loaded {len(selected_challenges)} challenges from index {start} to {end} (Total available: {total})")
    
    # Process batches
    batch_results = process_all_batches(
        selected_challenges,
        batch_size=batch_size,
        max_workers=max_workers,
        save_to_file=save_to_file,
        output_file=output_file
    )

    # Combine batch results (pass expected_total for cross-batch normalization)
    expected_total = sum(c.get('challenge_count', 1) for c in selected_challenges)
    combined = combine_batch_results(
        batch_results=batch_results,
        expected_total=expected_total,
        save_to_file=save_to_file,
        save_file_path=second_output_file
    )
    
    return batch_results, combined


def _ensure_challenge_dicts(data: list) -> List[Dict[str, Any]]:
    """Convert raw data (strings or dicts) into the standard challenge dict format."""
    result = []
    if not isinstance(data, list):
        return result
    for item in data:
        if isinstance(item, str) and item.strip():
            result.append({
                'challenge_text': item.strip(),
                'challenge_count': 1,
                'category': ''
            })
        elif isinstance(item, dict):
            # Support both old {'challenge': '...'} and new {'challenge_text': '...'} formats
            text = item.get('challenge_text') or item.get('challenge') or ''
            if isinstance(text, str) and text.strip():
                result.append({
                    'challenge_text': text.strip(),
                    'challenge_count': item.get('challenge_count', 1),
                    'category': item.get('category', '')
                })
    return result



def retry_if_result_none(result):
    return result is None


def get_clean_output(response) -> Optional[Dict[str, Any]]:
    """Parse LLM response and extract challenges + categories.
    """
    try:
        if isinstance(response, str):
            try:
                response = json_repair.repair_json(response, return_objects=True)
            except Exception:
                return None

        # Unwrap tool-call wrappers
        if isinstance(response, dict):
            if 'type' in response and 'value' in response:
                return get_clean_output(response.get('value'))
            
            # Unwrap common wrapper keys
            if 'parameters' in response:
                return get_clean_output(response.get('parameters'))
            if 'input' in response and 'unique_challenges' not in response:
                return get_clean_output(response.get('input'))
            
            # --- Main parsing: expect {unique_challenges: [...], categories: [...]} ---
            # LLM sometimes uses 'challenges' instead of 'unique_challenges'
            raw_challenges = response.get('unique_challenges') or response.get('challenges')
            raw_categories = response.get('categories')
            
            if raw_challenges is not None:
                challenges = _parse_challenge_items(raw_challenges)
                categories = _parse_category_items(raw_categories)
                if challenges:
                    return {"challenges": challenges, "categories": categories}
        
        # Handle case where LLM returns a plain list (backward compat)
        if isinstance(response, list):
            challenges = _parse_challenge_items(response)
            if challenges:
                return {"challenges": challenges, "categories": []}

        return None
    except Exception as e:
        print(f"Error in get_clean_output: {str(e)}")
        return None


def _parse_challenge_items(data) -> List[Dict[str, Any]]:
    """Parse a list of challenge items from LLM output.
    Handles both actual lists and stringified JSON arrays from tool-use responses.
    """
    # Handle stringified JSON (LLM sometimes returns arrays as strings in tool-use)
    if isinstance(data, str):
        try:
            data = json_repair.repair_json(data, return_objects=True)
        except Exception:
            return []
    
    if not isinstance(data, list):
        return []
    
    cleaned = []
    for item in data:
        if isinstance(item, dict):
            text = item.get('challenge_text', '')
            if isinstance(text, str) and text.strip():
                cleaned.append({
                    'challenge_text': text.strip(),
                    'challenge_count': item.get('challenge_count', 1),
                    'category': item.get('category', '')
                })
        elif isinstance(item, str) and item.strip():
            # Backward compat: plain string → wrap as dict with count 1
            cleaned.append({
                'challenge_text': item.strip(),
                'challenge_count': 1,
                'category': ''
            })
    return cleaned


def _parse_category_items(data) -> List[Dict[str, Any]]:
    """Parse category count items from LLM output.
    Handles: list of {category_name, category_count}, dict of {name: count},
    and stringified JSON versions of both.
    """
    # Handle stringified JSON
    if isinstance(data, str):
        try:
            data = json_repair.repair_json(data, return_objects=True)
        except Exception:
            return []
    
    # Handle dict format: {"Challenges": 83, "Positive Observations": 4, ...}
    if isinstance(data, dict):
        cleaned = []
        for name, count in data.items():
            if name and isinstance(count, (int, float)):
                cleaned.append({
                    'category_name': str(name),
                    'category_count': int(count)
                })
        return cleaned
    
    if not isinstance(data, list):
        return []
    
    cleaned = []
    for item in data:
        if isinstance(item, dict):
            name = item.get('category_name', '')
            count = item.get('category_count', 0)
            if name:
                cleaned.append({
                    'category_name': str(name),
                    'category_count': int(count) if count else 0
                })
    return cleaned



def _normalize_challenge_counts(challenges: List[Dict[str, Any]], expected_total: int) -> List[Dict[str, Any]]:
    """Normalize challenge counts so they sum to expected_total (scales both up and down).
    """
    if not challenges or expected_total <= 0:
        return challenges

    actual_total = sum(c.get('challenge_count', 1) for c in challenges)
    if actual_total == expected_total or actual_total == 0:
        return challenges

    ratio = expected_total / actual_total
    for c in challenges:
        c['challenge_count'] = max(1, round(c['challenge_count'] * ratio))

    # Fix any rounding drift (±1 or ±2) by adjusting the largest items
    diff = expected_total - sum(c['challenge_count'] for c in challenges)
    challenges.sort(key=lambda c: c['challenge_count'], reverse=True)
    for c in challenges:
        if diff == 0:
            break
        adj = 1 if diff > 0 else -1
        if c['challenge_count'] + adj >= 1:
            c['challenge_count'] += adj
            diff -= adj

    return challenges

def combine_batch_results(
    batch_results: Dict[str, Any] = None,
    expected_total: int = None,
    output_file_path: str = OUTPUT_FILE,
    save_to_file: bool = False,
    save_file_path: str = SECOND_OUTPUT_FILE
) -> Dict[str, Any]:
    """
    Combine batch-wise LLM output into a single result.
    If expected_total is provided, normalizes combined counts to match it.
    """
    all_challenges = []
    category_counts = defaultdict(int)
    
    # Use provided batch_results or load from file
    if batch_results is not None:
        challenges_dict = batch_results
    else:
        if not os.path.exists(output_file_path):
            print(f"⚠️ Warning: Output file {output_file_path} not found.")
            return {"challenges": [], "category_counts": {}}

        try:
            with open(output_file_path, "r") as f:
                challenges_dict = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {output_file_path}: {e}")
            return {"challenges": [], "category_counts": {}}

    # Combine challenges and aggregate category counts from all batches
    for _, batch_data in challenges_dict.items():
        if not isinstance(batch_data, dict):
            continue
        
        # Collect challenges
        challenges_list = batch_data.get("challenges")
        if isinstance(challenges_list, list):
            for challenge in challenges_list:
                if isinstance(challenge, dict) and challenge.get('challenge_text', '').strip():
                    all_challenges.append({
                        'challenge_text': challenge['challenge_text'].strip(),
                        'challenge_count': challenge.get('challenge_count', 1),
                        'category': challenge.get('category', '')
                    })
        
    # Normalize challenge counts to match expected_total (once, at combine level)
    if expected_total is not None:
        all_challenges = _normalize_challenge_counts(all_challenges, expected_total)

    # Compute category counts from the normalized challenge items (so both are consistent)
    for challenge in all_challenges:
        cat = challenge.get('category', '')
        if cat:
            category_counts[cat] += challenge.get('challenge_count', 1)

    # Save if requested
    if save_to_file:
        try:
            save_data = {
                "challenges": all_challenges,
                "category_counts": dict(category_counts)
            }
            with open(save_file_path, "w") as f:
                json.dump(save_data, f, indent=2)
            print(f"✅ Combined results saved to {save_file_path}")
        except Exception as e:
            print(f"❌ Error saving file: {e}")

    print(f"Combined challenges count: {len(all_challenges)}")
    return {
        "challenges": all_challenges,
        "category_counts": dict(category_counts)
    }


if __name__ == "__main__":
    run_unique_challenge_processing()
