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
INPUT_FILE = 'chatbot/scripts/common_challenges/district_challenge.json'
OUTPUT_FILE = 'chatbot/scripts/common_challenges/llm_district_challenges_output.json'
SECOND_OUTPUT_FILE = 'chatbot/scripts/common_challenges/flat_district_challenges_output.json'
BATCH_SIZE = 3
MAX_WORKERS = 2
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER'))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


def chunk_data(data: List[str], batch_size: int) -> List[List[str]]:
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def build_user_message(batch: List[str]) -> List[Dict[str, Any]]:
    challenges_text = "\n".join([f"- {challenge}" for challenge in batch])
    return [
        {
            'role': 'user',
            'content': [{
                'text': f"""Given the list of challenges below, Identify Top 3 common challenges observed:\n\n{challenges_text}\n\n"""
            }]
        }
    ]


def call_llm(batch: List[str], index: int) -> Dict[str, Any]:
    messages = build_user_message(batch)
    company_bot = CompanyBot.objects.filter(route='/district_challenges_script').first()
    if not company_bot:
        return {f"batch_{index}_error": "No Bot Found"}

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
        output=get_clean_output(response=output)

    key = f"challenge"
    return {key: output}


def extract_district_challenges(data: List[Dict[str, str]], district_name: str) -> List[str]:
    district_challenges = []
    for entry in data:
        challenge = entry.get(district_name)
        print("working onL ", challenge)
        if challenge:
            print("type working onL ", type(challenge))
            if isinstance(challenge, list):
                for item in challenge:
                    if item and isinstance(item, str) and item.strip():
                        district_challenges.append(item.strip())
            elif isinstance(challenge, str) and challenge.strip():
                district_challenges.append(challenge.strip())
    return district_challenges


def process_one_district_batches(district_name: str, challenges: List[str]):
    chunks = chunk_data(challenges, BATCH_SIZE)
    district_output = {}

    print(f"🚀 Starting {district_name} with {len(challenges)} challenges in {len(chunks)} batches")

    def run_one_batch(idx_batch):
        idx, batch = idx_batch
        print(f"[{district_name}] Running batch {idx}")
        result = call_llm(batch, idx)
        return idx, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(run_one_batch, (i, chunk)) for i, chunk in enumerate(chunks)]

        for future in tqdm(as_completed(futures), total=len(futures), desc=f"{district_name} Progress"):
            idx, result = future.result()
            key = f"top_challenge"
            batch_key = f"{key}_{idx}"
            district_output[batch_key] = result.get("challenge")

    # Load full existing file, update only district part
    full_output = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            try:
                full_output = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Warning: Output file corrupted. Starting fresh.")

    full_output[district_name] = district_output

    with open(OUTPUT_FILE, "w") as f:
        json.dump(full_output, f, indent=2)

    print(f"✅ Finished processing for {district_name}. Saved to {OUTPUT_FILE}")


# -------------- ENTRY POINT ------------------
def run_common_challenge_processing(district_name: str, input_file: str = INPUT_FILE):
    with open(input_file, "r") as f:
        all_data = json.load(f)
    if all_data and isinstance(all_data, dict):
        all_data = [all_data]

    challenges = extract_district_challenges(all_data, district_name)

    if not challenges:
        print(f"⚠️ No challenges found for district: {district_name}")
        return

    print(f"✅ Found {len(challenges)} challenges for {district_name}")
    process_one_district_batches(district_name, challenges)


def retry_if_result_none(result):
    return result is None


def get_clean_output(response):
    if response and isinstance(response, dict):
        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response.get('common_challenges')
    reason_content = response.get('reason_for_commonality')
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

    print("response_json_content: ", response_json_content)
    print("reason_content: ", reason_content)

    return response_json_content


def convert_district_challenges_to_flat_list(output_file_path=OUTPUT_FILE, save_file_path=SECOND_OUTPUT_FILE):
    district_challenges_output = {}

    # Check if output file exists
    if not os.path.exists(output_file_path):
        print(f"⚠️ Warning: Output file {output_file_path} not found.")
        return district_challenges_output

    # Read data from output file
    try:
        with open(output_file_path, "r") as f:
            district_challenges_dict = json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Warning: Output file {output_file_path} is corrupted or empty.")
        return district_challenges_output
    except Exception as e:
        print(f"❌ Error reading file {output_file_path}: {e}")
        return district_challenges_output

    # Iterate through all districts
    for district_name, district_batches in district_challenges_dict.items():
        # Initialize district list if not exists
        if district_name not in district_challenges_output:
            district_challenges_output[district_name] = []

        if isinstance(district_batches, dict):
            # Iterate through all batches for this district
            for batch_key, challenges_list in district_batches.items():
                # Check if the value is a list and not None
                if isinstance(challenges_list, list):
                    # Add each challenge string to the district's list
                    for challenge_text in challenges_list:
                        if challenge_text and isinstance(challenge_text, str):
                            district_challenges_output[district_name].append(challenge_text)
                elif challenges_list and isinstance(challenges_list, str):
                    # Handle case where challenges_list is a single string
                    district_challenges_output[district_name].append(challenges_list)

    print("district_challenges_output: ", district_challenges_output)
    print("Total districts: ", len(district_challenges_output))

    # Save the district challenges to a new file
    try:
        with open(save_file_path, "w") as f:
            json.dump(district_challenges_output, f, indent=2)
        print(f"✅ Converted district_challenges saved to {save_file_path}")
    except Exception as e:
        print(f"❌ Error saving to file {save_file_path}: {e}")

    return district_challenges_output
