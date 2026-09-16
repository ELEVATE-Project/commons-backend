import logging
import os
import requests

api_key = os.getenv("OPENAI_API_KEY")
logger = logging.getLogger("django")

OPENAI_HEADERS = {
    "Authorization": f"Bearer {api_key}",
    "OpenAI-Beta": "assistants=v2",
}

def get_vector_store_id(media):
    import json_repair
    tool = media.company_bot.tool_context
    if tool and isinstance(tool, str):
        tool = json_repair.repair_json(tool, return_objects=True)

    vector_store_id = None
    if tool and isinstance(tool, dict):
        tool_list = tool.get("tool")
        if isinstance(tool_list, list) and tool_list:
            first_tool = tool_list[0]
            if isinstance(first_tool, dict):
                vs_ids = first_tool.get("vector_store_ids")
                if isinstance(vs_ids, list) and vs_ids:
                    vector_store_id = vs_ids[0]
    if not vector_store_id:
        logger.error(
            f"Vector store ID not found in tool_context during delete. {media.id}"
        )
        return None
    return vector_store_id


def upload_file_to_openai(file_name, file_content):
    """Upload a file to OpenAI Files API"""
    try:
        response = requests.post(
            "https://api.openai.com/v1/files",
            headers=OPENAI_HEADERS,
            files={
                "file": (file_name, file_content),
            },
            data={
                "purpose": "assistants",
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()
        logger.info(f"OpenAI file upload response: {data}")
        return 200, data

    except Exception as e:
        logger.exception("Error while uploading file to OpenAI")
        return 500, None


def add_file_to_vector_store(media, metadata=None):
    """Add uploaded file to vector store with metadata"""

    attributes = {}
    if isinstance(metadata, dict):
        attributes = {
            str(k): str(v)
            for k, v in metadata.items()
            if v is not None
        }

    try:
        vector_store_id = get_vector_store_id(media)
        print("vector store id: ", vector_store_id)
        file_id = getattr(media, "external_file_id", None)
        print("file_id: ", file_id)
        if not file_id or not vector_store_id:
            return 500, None
        url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files"

        payload = {
            "file_id": file_id,
            "attributes": attributes,
        }

        response = requests.post(
            url,
            headers={**OPENAI_HEADERS, "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()
        logger.info(f"Vector store attach response: {data}")
        return 200, data

    except Exception as e:
        logger.exception(
            f"Failed to add file to vector store. File ID: {file_id}"
        )
        return 500, None


def delete_file_from_vector_store(media):
    """
    Remove a file from an OpenAI Vector Store
    """

    try:
        vector_store_id = get_vector_store_id(media)
        print("vector store id: ", vector_store_id)
        file_id = getattr(media, "external_file_id", None)
        print("file_id: ", file_id)
        if not file_id or not vector_store_id:
            return 500, None
        url = f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files/{file_id}"

        response = requests.delete(
            url,
            headers=OPENAI_HEADERS,
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()

        logger.info(f"Deleted file from vector store. file_id={file_id}, response={data}")
        return 200, data

    except Exception as e:
        logger.exception(f"Failed to delete file from vector store. file_id={file_id}")
        return 500, None
