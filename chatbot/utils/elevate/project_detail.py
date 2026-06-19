import os
import requests
import traceback

base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def fetch_existing_project_attachments(project_id, access_token):
    try:
        url = f"https://{base_url}/userProjects/details/{project_id}"
        print("Fetching attachments from URL:", url)

        headers = {
            "X-auth-token": access_token,
            "Content-Type": "application/json",
        }

        response = requests.post(url, headers=headers)
        response.raise_for_status()

        response_json = response.json()
        print("Project detail response received.")

        story = response_json.get("result", {}).get("story", {})
        existing_attachments = story.get("attachments", [])

        print("Existing attachments:", existing_attachments)
        return existing_attachments

    except Exception as e:
        print(f"Failed to fetch existing attachments: {str(e)}")
        traceback.print_exc()
        return []
