import json
import os
import uuid
import requests

from django.core.files.base import ContentFile
from django.conf import settings

from chatbot.models import (
    CompanyBot, Media, KeyValue, Tag, Company
)
from chatbot.models.media_models import MediaImage, MediaTypeChoices


def process_tags(tags_list):
    seen = set()
    unique_tags = []

    for tag in tags_list:
        tag_name = tag.get('name') if isinstance(tag, dict) else str(tag)
        if tag_name and tag_name not in seen:
            seen.add(tag_name)
            unique_tags.append(tag_name)

    return unique_tags


def get_or_create_tags(tag_names):
    tag_objects = []
    for tag_name in tag_names:
        tag, _ = Tag.objects.get_or_create(
            name=tag_name,
            defaults={'status': 'APPROVED', 'source_type': 'MANUAL'}
        )
        tag_objects.append(tag)
    return tag_objects


def attach_file_if_exists(media_obj, file_url):
    if not file_url:
        return

    try:
        print(f"Downloading file: {file_url}")
        response = requests.get(file_url, timeout=60)
        response.raise_for_status()

        file_name = file_url.split('/')[-1]
        media_obj.file.save(
            file_name,
            ContentFile(response.content),
            save=False
        )

        print(f"Attached file: {file_name}")

    except Exception as e:
        print(f"File download failed ({file_url}): {e}")


def save_media_node(media_data, company_bot, parent=None, organization=None):
    media = Media(
        name=media_data.get('name', ''),
        media_type=media_data.get('media_type', MediaTypeChoices.TXT.value),
        description=media_data.get('description', ''),
        priority=media_data.get('priority', 'P1'),
        company_bot_id=company_bot.id,
        organization=organization,
        extracted_text=media_data.get('extracted_text', ''),
        parent=parent
    )

    attach_file_if_exists(media, media_data.get('file_url'))

    media.save()
    print(f"Saved Media ID={media.id}, Parent={parent.id if parent else None}")

    tags = process_tags(media_data.get('tags', []))
    if tags:
        media.tags.set(get_or_create_tags(tags))

    kvs = [
        KeyValue(
            media=media,
            key=kv.get('key', ''),
            value=kv.get('value', '')
        )
        for kv in media_data.get('key_values', [])
        if isinstance(kv, dict)
    ]
    if kvs:
        KeyValue.objects.bulk_create(kvs)

    images = [
        MediaImage(
            media=media,
            image_url=img.get('image_url', ''),
            caption=img.get('caption', '')
        )
        for img in media_data.get('images', [])
        if isinstance(img, dict)
    ]
    if images:
        MediaImage.objects.bulk_create(images, ignore_conflicts=True)

    for subdoc_data in media_data.get('subdocuments', []):
        save_media_node(
            media_data=subdoc_data,
            company_bot=company_bot,
            parent=media,
            organization=organization
        )

    return media


def batch_reingest_from_export(json_path, limit=None, start_index=0):
    if not os.path.exists(json_path):
        raise ValueError(f"JSON file not found: {json_path}")

    company_bot = CompanyBot.objects.get(route="/tag_extractor")

    with open(json_path) as f:
        items = json.load(f)

    items = items[start_index:]
    if limit:
        items = items[:limit]

    session_id = str(uuid.uuid4())

    print("=" * 60)
    print("Batch Re-ingest Started")
    print(f"Items: {len(items)}")
    print(f"Session ID: {session_id}")
    print("=" * 60)

    success = 0
    failures = []

    for idx, media_data in enumerate(items, start=1):
        print(f"\n[{idx}] Processing: {media_data.get('name')}")

        try:
            organization = Company.objects.filter(
                slug=media_data.get('organization')
            ).first()

            save_media_node(
                media_data=media_data,
                company_bot=company_bot,
                parent=None,
                organization=organization
            )

            success += 1
            print("✓ Success")

        except Exception as e:
            print(f"✗ Failed: {e}")
            failures.append({
                "name": media_data.get('name'),
                "error": str(e)
            })

    print("\n" + "=" * 60)
    print("Batch Re-ingest Completed")
    print(f"Success: {success}")
    print(f"Failed: {len(failures)}")
    print("=" * 60)

    return {
        "session_id": session_id,
        "total": len(items),
        "successful": success,
        "failed": len(failures),
        "failures": failures
    }
