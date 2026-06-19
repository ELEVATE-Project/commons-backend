import base64
import os
import requests
from chatbot.models import StoryMedia, MediaTypeChoices
from django.db.models import Q
from django.db import transaction


base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def get_file_names_for_story(story):
    """Retrieve file names for a specific story."""
    return StoryMedia.objects.filter(story=story, media_type=MediaTypeChoices.PDF).first()


def get_file_names_for_session(session_value):
    """Retrieve file names for a specific session."""
    return StoryMedia.objects.filter(
        Q(story__session=session_value, include_in_story=True) |
        Q(story__session=session_value, media_type=MediaTypeChoices.PDF)
    )


def prepare_request_data(session_value, file_names):
    """Prepare request data for the cloud service."""
    return {
        "request": {
            session_value: {
                "files": file_names
            }
        }
    }


def perform_cloud_upload(file_info, pdf_file):
    """Upload a file to the cloud using base64-encoded data."""
    presigned_url = file_info["url"]

    response = requests.put(
        presigned_url,
        data=pdf_file,
        headers={"Content-Type": "multipart/form-data", "x-ms-blob-type": "BlockBlob",}
    )
    print(response)
    print(response.status_code)
    if response.status_code in [200, 201]:
        print(f"File uploaded successfully")
        return True
    else:
        print(f"Failed to upload file: {response.status_code}, {response.text}")
        return False


def update_story_media_source_path(file_name, source_path):
    """Update the source path for a file in the database."""
    StoryMedia.objects.filter(name=file_name).update(source_path=source_path)


def handle_cloud_response(results, session_value, story=None, instance=None):
    """Handle the cloud response and save data."""
    attachments = []
    pdf_information = []

    if story:
        for file_info in results.get(session_value, {}).get("files", []):
            source_path = file_info["payload"]["sourcePath"]
            update_story_media_source_path(file_info["file"], source_path)
            story_media_file = get_file_names_for_story(story)
            print("story_media_file: ", story_media_file)
            if not story_media_file:
                print(f"No story file found for story ID: {story.id}")
            else:
                print(f"Story file: {story_media_file.name}")
            pdf_file = story_media_file.file
            if not pdf_file:
                print(f"No pdf_file found for story ID: {story.id}")
            else:
                print(f"Pdf file: {pdf_file}")
            print("pdf_file type: ", type(pdf_file))
            if perform_cloud_upload(file_info, pdf_file):
                pdf_information.append({
                    "filePath": source_path,
                    "language": story.language
                })

        return {"attachments": attachments, "pdfInformation": pdf_information}

    if instance:
        file_name = instance.get("name")
        file_info = results.get(session_value, {}).get("files", [])[0]
        print("file_info: ", file_info)
        source_path = file_info["payload"]["sourcePath"]
        file_data = instance.get("base64_str")
        print('source path: ', source_path)

        binary_data = base64.b64decode(file_data)

        update_story_media_source_path(file_name, source_path)
        print('file_info["url"]: ', file_info["url"])

        response = requests.put(
            file_info["url"],
            data=binary_data,
            headers={
                "Content-Type": "multipart/form-data",
                "Access-Control-Allow-Origin": "*",
                "x-ms-blob-type": "BlockBlob",
            }
        )
        print('cloud response: ', response)

        if response.status_code == 200:
            print(f"File uploaded successfully: {file_name}")
        else:
            print(f"Failed to upload file {file_name}: {response.status_code}, {response.text}")

        attachments.append({
            "name": file_name,
            "sourcePath": source_path,
            "type": instance.get("media_type")
        })
        return {"attachments": attachments, "pdfInformation": pdf_information}

    for session_id, session_data in results.items():
        if session_id == "cloudStorage":
            continue
        for file_info in session_data.get("files", []):
            file_name = file_info["file"]
            source_path = file_info["payload"]["sourcePath"]
            base64_data = None
            file_record = StoryMedia.objects.filter(name=file_name).first()

            if file_record:
                update_story_media_source_path(file_name, source_path)
                base64_data = file_record.base64_str

            if base64_data and perform_cloud_upload(file_info, base64_data):
                if file_name.lower().endswith(".pdf"):
                    pdf_information.append({
                        "filePath": source_path,
                        "language": story.language
                    })
                else:
                    attachments.append({
                        "name": file_name,
                        "sourcePath": source_path,
                        "type": file_record.media_type
                    })

    return {"attachments": attachments, "pdfInformation": pdf_information}


def upload_to_cloud(session_value, access_token, story=None, instance=None):
    """Main function to upload files to the cloud."""
    url = f"https://{base_url}/cloud-services/files/preSignedUrls"
    print("---------------------")
    print("Upload Cloud Url: ", url)
    print("---------------------")
    if access_token.startswith('"') and access_token.endswith('"'):
        access_token = access_token[1:-1]
    headers = {"X-auth-token": access_token}

    if story:
        story_file_name = get_file_names_for_story(story)
        file_names = [story_file_name.name if story_file_name else "sample"]
    elif instance:
        if not instance.get("include_in_story") and instance.get("media_type") != MediaTypeChoices.PDF:
            return
        file_names = [instance.get("name")]
    else:
        file_names = [file.name for file in get_file_names_for_session(session_value)]

    data = prepare_request_data(session_value, file_names)
    print("presigned: upload data: ", data)
    response = None
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        print('response text: ', response.json())

        results = response.json().get("result", {})
        with transaction.atomic():
            return handle_cloud_response(results, session_value, story=story, instance=instance)
    except requests.exceptions.RequestException as e:
        print(f"Error during cloud request: {e}")
        response.raise_for_status()
        return None
