import os
import requests
import time
from chatbot.models import CompanyBot

# Configuration
BOT_ROUTE = "/free-flow-bot"
api_key = os.getenv('OPENAI_API_KEY')

OPENAI_HEADERS = {
    "Authorization": f"Bearer {api_key}",
    "OpenAI-Beta": "assistants=v2",
}

# Get vector store ID
import json_repair

company_bot = CompanyBot.objects.filter(route=BOT_ROUTE).first()
tool = company_bot.tool_context
if tool and isinstance(tool, str):
    tool = json_repair.repair_json(tool, return_objects=True)

vector_store_id = tool.get("tool")[0].get("vector_store_ids")[0]
print(f"✅ Vector Store ID: {vector_store_id}")

list_url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files"

total_deleted = 0
iteration = 0
max_iterations = 100  # Safety limit

while iteration < max_iterations:
    iteration += 1

    # Fetch files
    response = requests.get(list_url, headers=OPENAI_HEADERS, timeout=60)
    response.raise_for_status()
    files = response.json().get('data', [])

    if not files:
        print(f"\n🎉 Vector store is empty! Total deleted: {total_deleted}")
        break

    print(f"\n{'=' * 80}")
    print(f"ITERATION {iteration}: Found {len(files)} files")
    print(f"{'=' * 80}")

    # Delete all files in this batch
    deleted = 0
    failed = 0

    for i, file in enumerate(files):
        file_id = file.get('id')
        try:
            delete_url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files/{file_id}"
            delete_response = requests.delete(delete_url, headers=OPENAI_HEADERS, timeout=60)

            if delete_response.ok:
                deleted += 1
                total_deleted += 1
                print(f"✅ [{i + 1}/{len(files)}] Deleted: {file_id}")
            else:
                failed += 1
                print(f"❌ [{i + 1}/{len(files)}] Failed: {file_id} - {delete_response.text}")

        except Exception as e:
            failed += 1
            print(f"❌ [{i + 1}/{len(files)}] Error: {file_id} - {str(e)}")

    print(f"\nIteration {iteration} summary: Deleted {deleted}, Failed {failed}")

    # Small delay before next iteration
    time.sleep(1)

if iteration >= max_iterations:
    print(f"\n⚠️  Reached max iterations ({max_iterations}). Files might still remain.")
else:
    print(f"\n✅ All done! Total iterations: {iteration}, Total deleted: {total_deleted}")

# Final verification
verify_response = requests.get(list_url, headers=OPENAI_HEADERS, timeout=60)
remaining = len(verify_response.json().get('data', []))
print(f"🔍 Final count - Files remaining: {remaining}")
