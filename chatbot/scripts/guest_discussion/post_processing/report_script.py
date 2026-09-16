from typing import List, Dict, Any
from tqdm import tqdm
from chatbot.models import CompanyBot
import json
import os
import json_repair
from retrying import retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from chatbot.utils.llm import LLM
from chatbot.models.enums import LLMProvider
from chatbot.llm_models.llm_script import handle_bedrock_model


# -------------- CONFIG ------------------
INPUT_FILE = 'chatbot/scripts/report/ReportList.json'
OUTPUT_FILE = 'chatbot/scripts/report/final_output.json'
MAX_WORKERS = 4
BATCH_SIZE = 20
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
# -------------- LLM CALL ------------------

def build_prompt(challenges: List[str], solutions: List[str]) -> List[Dict[str, Any]]:
    challenge_str = "\n".join([f"{i+1}. {c}" for i, c in enumerate(challenges)])
    solution_str = "\n".join([f"{i+1}. {s}" for i, s in enumerate(solutions)])

    message = f"""
    These are the challenges and solution from the report:
CHALLENGES:
{challenge_str}

SOLUTIONS:
{solution_str}
"""
    return [{"role": "user", "content": [{"text": message.strip()}]}]


def chunk_data(data: List[Any], batch_size: int) -> List[List[Any]]:
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def process_stories_parallel(stories: List[Dict[str, Any]]) -> None:
    results = {}

    # Load existing output
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Output file is corrupted. Starting fresh.")

    processed_ids = set(results.keys())
    remaining_stories = [s for s in stories if s["id"] not in processed_ids]
    story_batches = chunk_data(remaining_stories, BATCH_SIZE)

    print(f"🔧 Processing {len(story_batches)} batches with {MAX_WORKERS} workers (batch size = {BATCH_SIZE})...")

    def process_one_batch(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        batch_results = {}
        for story in batch:
            story_result = call_llm_for_story(story)
            batch_results.update(story_result)
        return batch_results

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_one_batch, batch) for batch in story_batches]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing Story Batches"):
            batch_output = future.result()
            results.update(batch_output)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"✅ Output saved to {OUTPUT_FILE}")


def call_llm_for_story(story: Dict[str, Any]) -> Dict[str, Any]:
    story_id = story["id"]
    data = json.loads(story["data"])
    challenges = data.get("challenges", [])
    solutions = data.get("solutions", [])

    if not challenges or not solutions:
        return {story_id: {"reorder_steps": []}}

    messages = build_prompt(challenges, solutions)
    company_bot = CompanyBot.objects.filter(route='/script_report').first()
    if not company_bot:
        return {story_id: {"error": "No bot found"}}

    tools = company_bot.tool_context
    if tools and isinstance(tools, str):
        tools = json_repair.repair_json(tools, return_objects=True)

    formatted_prompt = [{"text": company_bot.context}]
    response = handle_bedrock_model(
        system_prompt=formatted_prompt,
        messages=messages,
        model_name=company_bot.llm_model,
        temperature=company_bot.bot_temperature,
        max_token=company_bot.max_token,
        company_bot=company_bot,
        tools=tools
    )
    cleaned = get_clean_output(response=response)
    return {story_id: {"reorder_steps": cleaned}}

# -------------- MAIN ------------------

def run_story_matcher(input_file: str = INPUT_FILE):
    with open(input_file, "r") as f:
        data = json.load(f)

    print(f"🚀 Loaded {len(data)} stories")
    process_stories_parallel(data)



def retry_if_result_none(result):
    return result is None

def get_clean_output(response):
    if response and isinstance(response, dict):
        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response.get('reorder_steps')
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    if isinstance(response_json_content, dict) and response_json_content.get("type"):
        if "value" in response_json_content:
            value = response_json_content.get("value")
        elif "parameters" in response_json_content:
            value = response_json_content.get("parameters")
        else:
            value = None
        if value and isinstance(value, str) and value.strip():
            value = json_repair.repair_json(value, return_objects=True)
            response_json_content = value
        else:
            response_json_content = {}

    # print("response_json_content: ", response_json_content)

    return response_json_content