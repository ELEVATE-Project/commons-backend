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
from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.constants.post_processing_constants import SOLUTION_CATEGORIES

logger = logging.getLogger('django')


# -------------- CONFIG ------------------
INPUT_FILE = 'chatbot/scripts/solutions/all_solutions.json'
OUTPUT_FILE = 'chatbot/scripts/solutions/llm_unique_solutions_output.json'
SECOND_OUTPUT_FILE = 'chatbot/scripts/solutions/flat_solutions_output.json'
DEFAULT_BATCH_SIZE = 5
DEFAULT_MAX_WORKERS = 2
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', '3'))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# -------------- CORE FUNCTIONS ------------------

def chunk_data(data: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
    """Split list of solution dicts into batches."""
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def build_user_message(batch: List[Dict[str, Any]], company_bot) -> List[Dict[str, Any]]:

    solutions_text = "\n".join(
        [f"- [count: {item['solution_count']}] {item['solution_text']}" for item in batch]
    )
    
    categories_list = ", ".join(SOLUTION_CATEGORIES)
    
    # Render the tag_context Jinja2 template with variables
    context_data = {
        "solutions_text": solutions_text,
        "categories_list": categories_list,
    }
    
    template = Template(company_bot.tag_context)
    prompt_text = template.render(context_data)
    
    logger.info(f"[solution_script] Rendered prompt for batch (first 500 chars): {prompt_text[:500]}")
    
    return [
        {
            'role': 'user',
            'content': [{
                'text': prompt_text
            }]
        }
    ]

def call_llm(batch: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
    try:
        company_bot = CompanyBot.objects.filter(route='/solutions_script').first()
        if not company_bot:
            logger.error("[solution_script] CompanyBot with route '/solutions_script' not found.")
            return {"solutions": None, "categories": None}

        if not company_bot.tag_context:
            logger.error("[solution_script] tag_context is empty for CompanyBot route='/solutions_script'. Please set the prompt template in admin.")
            return {"solutions": None, "categories": None}

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

        # output = handle_openai_model(
        #     messages=messages,
        #     temperature=0.0,
        #     max_token=32768,
        #     top_p=1.0,
        #     model_name=LLMModel.GPT4_1_MINI,
        #     key_name='OPENAI_API_KEY',
        #     is_actual_key=False
        # )

        if output:
            parsed = get_clean_output(response=output)
            return parsed if parsed else {"solutions": None, "categories": None}

        return {"solutions": None, "categories": None}
    except Exception as e:
        print(f"Error in call_llm for batch {index}: {str(e)}")
        return {"solutions": None, "categories": None}


def process_all_batches(
    data: List[Dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    save_to_file: bool = False,
    output_file: str = OUTPUT_FILE
) -> Dict[str, Any]:
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
            batch_key = f"solution_{idx}"
            results[batch_key] = {
                "solutions": result.get("solutions"),
                "categories": result.get("categories")
            }

    if save_to_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Saved {len(chunks)} batches to {output_file}")

    return results


# -------------- ENTRY POINT ------------------
def run_unique_solution_processing(
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
    # Get solutions from input_data or input_file
    if input_data is not None:
        solutions = input_data
    elif input_file:
        with open(input_file, "r") as f:
            raw = json.load(f)
        solutions = _ensure_solution_dicts(raw)
    else:
        input_file = INPUT_FILE
        with open(input_file, "r") as f:
            raw = json.load(f)
        solutions = _ensure_solution_dicts(raw)

    total = len(solutions)
    end = end if end is not None else total
    selected_solutions = solutions[start:end]

    print(f"🚀 Loaded {len(selected_solutions)} solutions from index {start} to {end} (Total available: {total})")
    
    # Process batches
    batch_results = process_all_batches(
        selected_solutions,
        batch_size=batch_size,
        max_workers=max_workers,
        save_to_file=save_to_file,
        output_file=output_file
    )

    # Combine batch results (pass expected_total for cross-batch normalization)
    expected_total = sum(c.get('solution_count', 1) for c in selected_solutions)
    combined = combine_batch_results(
        batch_results=batch_results,
        expected_total=expected_total,
        save_to_file=save_to_file,
        save_file_path=second_output_file
    )
    
    return batch_results, combined


def _ensure_solution_dicts(data: list) -> List[Dict[str, Any]]:
    """Convert raw data (strings or dicts) into the standard solution dict format."""
    result = []
    if not isinstance(data, list):
        return result
    for item in data:
        if isinstance(item, str) and item.strip():
            result.append({
                'solution_text': item.strip(),
                'solution_count': 1,
                'category': ''
            })
        elif isinstance(item, dict):
            # Support both old {'solution': '...'} and new {'solution_text': '...'} formats
            text = item.get('solution_text') or item.get('solution') or ''
            if isinstance(text, str) and text.strip():
                result.append({
                    'solution_text': text.strip(),
                    'solution_count': item.get('solution_count', 1),
                    'category': item.get('category', '')
                })
    return result



def retry_if_result_none(result):
    return result is None


def get_clean_output(response) -> Optional[Dict[str, Any]]:
    """Parse LLM response and extract solutions + categories."""
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
            if 'input' in response and 'unique_solutions' not in response:
                return get_clean_output(response.get('input'))
            
            # --- Main parsing: expect {unique_solutions: [...], categories: [...]} ---
            # LLM sometimes uses 'solutions' instead of 'unique_solutions'
            raw_solutions = response.get('unique_solutions') or response.get('solutions')
            raw_categories = response.get('categories')
            
            if raw_solutions is not None:
                solutions = _parse_solution_items(raw_solutions)
                categories = _parse_category_items(raw_categories)
                if solutions:
                    return {"solutions": solutions, "categories": categories}
        
        # Handle case where LLM returns a plain list (backward compat)
        if isinstance(response, list):
            solutions = _parse_solution_items(response)
            if solutions:
                return {"solutions": solutions, "categories": []}

        return None
    except Exception as e:
        print(f"Error in get_clean_output: {str(e)}")
        return None


def _parse_solution_items(data) -> List[Dict[str, Any]]:
    """Parse a list of solution items from LLM output.
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
            text = item.get('solution_text', '')
            if isinstance(text, str) and text.strip():
                cleaned.append({
                    'solution_text': text.strip(),
                    'solution_count': item.get('solution_count', 1),
                    'category': item.get('category', '')
                })
        elif isinstance(item, str) and item.strip():
            # Backward compat: plain string → wrap as dict with count 1
            cleaned.append({
                'solution_text': item.strip(),
                'solution_count': 1,
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
    
    # Handle dict format: {"Solution Proposals": 83, ...}
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



def _normalize_solution_counts(solutions: List[Dict[str, Any]], expected_total: int) -> List[Dict[str, Any]]:
    """Normalize solution counts so they sum to expected_total (scales both up and down)."""
    if not solutions or expected_total <= 0:
        return solutions

    actual_total = sum(c.get('solution_count', 1) for c in solutions)
    if actual_total == expected_total or actual_total == 0:
        return solutions

    ratio = expected_total / actual_total
    for c in solutions:
        c['solution_count'] = max(1, round(c['solution_count'] * ratio))

    # Fix any rounding drift (±1 or ±2) by adjusting the largest items
    diff = expected_total - sum(c['solution_count'] for c in solutions)
    solutions.sort(key=lambda c: c['solution_count'], reverse=True)
    for c in solutions:
        if diff == 0:
            break
        adj = 1 if diff > 0 else -1
        if c['solution_count'] + adj >= 1:
            c['solution_count'] += adj
            diff -= adj

    return solutions

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
    all_solutions = []
    category_counts = defaultdict(int)
    
    # Use provided batch_results or load from file
    if batch_results is not None:
        solutions_dict = batch_results
    else:
        if not os.path.exists(output_file_path):
            print(f"⚠️ Warning: Output file {output_file_path} not found.")
            return {"solutions": [], "category_counts": {}}

        try:
            with open(output_file_path, "r") as f:
                solutions_dict = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {output_file_path}: {e}")
            return {"solutions": [], "category_counts": {}}

    # Combine solutions and aggregate category counts from all batches
    for _, batch_data in solutions_dict.items():
        if not isinstance(batch_data, dict):
            continue
        
        # Collect solutions
        solutions_list = batch_data.get("solutions")
        if isinstance(solutions_list, list):
            for solution in solutions_list:
                if isinstance(solution, dict) and solution.get('solution_text', '').strip():
                    all_solutions.append({
                        'solution_text': solution['solution_text'].strip(),
                        'solution_count': solution.get('solution_count', 1),
                        'category': solution.get('category', '')
                    })
        
    # Normalize solution counts to match expected_total (once, at combine level)
    if expected_total is not None:
        all_solutions = _normalize_solution_counts(all_solutions, expected_total)

    # Compute category counts from the normalized solution items (so both are consistent)
    for solution in all_solutions:
        cat = solution.get('category', '')
        if cat:
            category_counts[cat] += solution.get('solution_count', 1)

    # Save if requested
    if save_to_file:
        try:
            save_data = {
                "solutions": all_solutions,
                "category_counts": dict(category_counts)
            }
            with open(save_file_path, "w") as f:
                json.dump(save_data, f, indent=2)
            print(f"✅ Combined results saved to {save_file_path}")
        except Exception as e:
            print(f"❌ Error saving file: {e}")

    print(f"Combined solutions count: {len(all_solutions)}")
    return {
        "solutions": all_solutions,
        "category_counts": dict(category_counts)
    }


if __name__ == "__main__":
    run_unique_solution_processing()
