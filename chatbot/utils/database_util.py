import json
from datetime import datetime

import requests
import os

from chatbot.constants.constants import VECTOR_DB_UPLOAD_TIMEOUT_SECONDS, VECTOR_DB_VERIFY_TIMEOUT_SECONDS

DATABASE_INTERFACE_BEARER_TOKEN = os.getenv('DATABASE_INTERFACE_BEARER_TOKEN')

SEARCH_TOP_K = 3

base_url = os.getenv('VECTOR_DB_BASE_URL')


def upsert_single_file(filename, file, metadata, media):
    url = f"{base_url}/api/documents"
    print("url: ", url)
    if isinstance(metadata, dict):
        metadata_json = json.dumps(metadata)
    else:
        metadata_json = metadata

    # Build payload with new format
    payload = {
        'metadata': metadata_json,
        'source_id': str(media.id),
        'priority': media.priority
    }
    
    # Add company_id if available
    if hasattr(media, 'organization') and media.organization:
        payload['company_id'] = media.organization.slug
    
    # Add title if available (from KeyValue or media name)
    title = None
    if hasattr(media, 'key_values'):
        from chatbot.models import KeyValue
        title_kv = KeyValue.objects.filter(media=media, key__iexact='TITLE').first()
        if title_kv:
            title = title_kv.value
    if not title:
        title = media.name
    if title:
        payload['title'] = title
    
    # Add summary if available (from description)
    if hasattr(media, 'description') and media.description:
        payload['summary'] = media.description

    if media.primary_theme_id:
        payload['theme'] = media.primary_theme_id
    
    # Add tags if available
    if hasattr(media, 'tags'):
        tags_list = list(media.tags.values_list('name', flat=True))
        if tags_list:
            payload['tags'] = json.dumps(tags_list)
    
    files = [
        ('file', (filename, file, media.media_type))
    ]
    headers = {
        'accept': 'application/json',
    }
    print("payload: ", payload)

    try:
        response = requests.request(
            "POST",  url, headers=headers, data=payload,
            files=files, timeout=300
        )

        print(f"Response status code: {response.status_code}")

        try:
            response_json = response.json()
            print("upserted: ", response_json)
            return response.status_code, json.dumps(response_json)
        except requests.exceptions.JSONDecodeError:
            print(f"Non-JSON response received. Status: {response.status_code}")
            print(f"Response headers: {response.headers}")
            print(f"Response content preview: {response.text[:500] if response.text else 'Empty'}")

            return response.status_code, response.text

    except requests.exceptions.Timeout:
        print(f"Request timeout after 60 seconds for media ID: {media.id}")
        return 504, "Request timeout"
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error for media ID {media.id}: {str(e)}")
        return 503, f"Connection error: {str(e)}"
    except Exception as e:
        print(f"Unexpected error for media ID {media.id}: {str(e)}")
        return 500, f"Unexpected error: {str(e)}"


def delete_single_file(media_id, company_slug=None):
    url = f"{base_url}/api/documents/{media_id}"

    params = {'company_id': company_slug} if company_slug else {}

    headers = {
        'accept': 'application/json',
    }
    response = requests.request("DELETE", url, headers=headers, params=params)
    print("deleted: ", response.json())
    return response.status_code, response.text


def update_single_file(media_id, filename, file, metadata, media):
    """Replace an existing document in the vector database"""
    url = f"{base_url}/api/documents/{media_id}"

    if isinstance(metadata, dict):
        metadata_json = json.dumps(metadata)
    else:
        metadata_json = metadata

    # Add updated_at timestamp
    if isinstance(metadata, dict):
        metadata['updated_at'] = str(datetime.now())
        metadata_json = json.dumps(metadata)

    payload = {
        'metadata': metadata_json,
        'priority': media.priority
    }

    if hasattr(media, 'organization') and media.organization:
        payload['company_id'] = media.organization.slug
    
    # Add title if available (from KeyValue or media name)
    title = None
    if hasattr(media, 'key_values'):
        from chatbot.models import KeyValue
        title_kv = KeyValue.objects.filter(media=media, key__iexact='TITLE').first()
        if title_kv:
            title = title_kv.value
    if not title:
        title = media.name
    if title:
        payload['title'] = title
    
    # Add summary if available (from description)
    if hasattr(media, 'description') and media.description:
        payload['summary'] = media.description

    if media.primary_theme_id:
        payload['theme'] = media.primary_theme_id
    
    # Add tags if available
    if hasattr(media, 'tags'):
        tags_list = list(media.tags.values_list('name', flat=True))
        if tags_list:
            payload['tags'] = json.dumps(tags_list)

    files = [
        ('file', (filename, file, media.media_type))
    ]
    headers = {
        'accept': 'application/json',
    }

    print("update payload: ", payload)
    try:
        response = requests.request(
            "PUT", url, headers=headers, data=payload, files=files, timeout=VECTOR_DB_UPLOAD_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout:
        return 504, f"Request timeout after {VECTOR_DB_UPLOAD_TIMEOUT_SECONDS} seconds"
    except requests.exceptions.ConnectionError as e:
        return 503, f"Connection error: {str(e)}"
    except Exception as e:
        return 500, f"Unexpected error: {str(e)}"
    print("updated: ", response.status_code, response.text[:500])
    return response.status_code, response.text


def is_document_indexed(source_id):
    """True/False when the vector database answers, None when it cannot be asked"""
    try:
        response = requests.post(
            f"{base_url}/api/documents/verify-sources", json={'source_ids': [str(source_id)]},
            timeout=VECTOR_DB_VERIFY_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return str(source_id) in response.json().get('found', [])
    except Exception as e:
        print(f"Could not verify source_id {source_id} in vector DB: {e}")
        return None
