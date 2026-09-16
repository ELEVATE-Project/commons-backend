"""
Google Cloud Translation glossary helpers (CSV → GCS → create glossary).

Used from Django admin after Voice rows are saved. Runtime translation reads
glossary_id + location from Voice.other_params via google_translate.py (unchanged).
"""
from __future__ import annotations

import csv
import io
import logging
import os
from typing import Any, List, Optional, Tuple

from django.conf import settings
from google.api_core.exceptions import NotFound
from google.cloud import storage, translate
from google.oauth2 import service_account

from chatbot.models.company_models import Voice
from chatbot.translate.google import google_translate

logger = logging.getLogger("django")


def normalize_glossary_entries(raw: Any) -> List[Tuple[str, str]]:
    """Canonical (source, target) pairs for change detection and CSV build."""
    if not raw or not isinstance(raw, list):
        return []
    pairs: List[Tuple[str, str]] = []
    for row in raw:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            src, tgt = str(row[0]).strip(), str(row[1]).strip()
        elif isinstance(row, dict):
            src = str(row.get("source", "")).strip()
            tgt = str(row.get("target", "")).strip()
        else:
            continue
        if not src and not tgt:
            continue
        pairs.append((src, tgt))
    return sorted(pairs)


def build_csv(entries: List[Tuple[str, str]]) -> str:
    """Unidirectional glossary CSV (no header): one source,target per row."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for src, tgt in entries:
        writer.writerow([src, tgt])
    return buf.getvalue()


def _glossary_bucket_name() -> Optional[str]:
    return os.environ.get("GLOSSARY_GCS_BUCKET") or os.environ.get("GCS_BUCKET_NAME")


def upload_csv(project_id: str, bucket_name: str, object_name: str, csv_text: str) -> str:
    credentials = service_account.Credentials.from_service_account_file(settings.SECRETS_JSON_PATH)
    client = storage.Client(project=project_id, credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(csv_text, content_type="text/csv")
    return f"gs://{bucket_name}/{object_name}"


def delete_glossary_if_exists(client: translate.TranslationServiceClient, glossary_resource_name: str) -> None:
    try:
        operation = client.delete_glossary(name=glossary_resource_name)
        operation.result(timeout=180)
        logger.info("Deleted existing glossary: %s", glossary_resource_name)
    except NotFound:
        logger.debug("No existing glossary to delete: %s", glossary_resource_name)
    except Exception:
        logger.error(
            "Failed while deleting glossary: %s",
            glossary_resource_name,
            exc_info=True
        )


def create_glossary(
    client: translate.TranslationServiceClient,
    parent: str,
    glossary_id: str,
    source_language_code: str,
    target_language_code: str,
    gcs_uri: str,
) -> translate.Glossary:
    glossary_name = f"{parent}/glossaries/{glossary_id}"
    glossary = translate.Glossary(
        name=glossary_name,
        language_pair=translate.Glossary.LanguageCodePair(
            source_language_code=source_language_code,
            target_language_code=target_language_code,
        ),
        input_config=translate.GlossaryInputConfig(
            gcs_source=translate.GcsSource(input_uri=gcs_uri)
        ),
    )
    operation = client.create_glossary(parent=parent, glossary=glossary)
    result = operation.result(timeout=180)
    logger.info("Glossary created: %s entry_count=%s", result.name, result.entry_count)
    return result


def sync_glossary_for_voice(voice: Voice) -> None:
    """
    Build CSV from other_params['glossary_entries'], upload to GCS, recreate glossary in GCP,
    then persist glossary_id and location via queryset update (avoids Voice.save() side effects).
    """
    params = dict(voice.other_params or {})
    entries = normalize_glossary_entries(params.get("glossary_entries"))
    if not entries:
        return

    project_id = (getattr(settings, "SECRETS", None) or {}).get("project_id")
    if not project_id:
        raise ValueError("project_id missing from settings.SECRETS; cannot sync glossary")

    bucket_name = _glossary_bucket_name()
    if not bucket_name:
        raise ValueError(
            "GCS bucket not configured: set GLOSSARY_GCS_BUCKET or GCS_BUCKET_NAME in the environment"
        )

    source_lang = (params.get("glossary_source_language_code") or "en").strip()
    target_lang = (params.get("glossary_target_language_code") or "te").strip()
    location = (params.get("location") or "us-central1").strip()

    glossary_id = (params.get("glossary_id") or "").strip()
    if not glossary_id:
        glossary_id = f"glossary-voice-{voice.id}-{source_lang}-{target_lang}".lower().replace("_", "-")

    csv_text = build_csv(entries)
    object_name = f"glossaries/voices/{voice.id}/{glossary_id}.csv"
    gcs_uri = upload_csv(project_id, bucket_name, object_name, csv_text)

    client = google_translate._get_client()
    parent = f"projects/{project_id}/locations/{location}"
    glossary_resource_name = f"{parent}/glossaries/{glossary_id}"
    delete_glossary_if_exists(client, glossary_resource_name)
    create_glossary(client, parent, glossary_id, source_lang, target_lang, gcs_uri)

    params["glossary_id"] = glossary_id
    params["location"] = location
    Voice.objects.filter(pk=voice.pk).update(other_params=params)
    voice.other_params = params

    logger.info(
        "Google glossary synced successfully for Voice id=%s glossary_id=%s",
        voice.pk,
        glossary_id
    )