# 🚀 Commons-Backend [Release 1.0.0]

## ✨ Features & Improvements

-   **Google Drive Integration for Decentralised Media Uploads**
    Introduced a decentralised upload approach where organizations connect their own Google Drive via OAuth 2.0 (with PKCE) and import entire Drive folders as knowledge-base media, instead of uploading files manually one by one.

-   **Drive Folder Import with Validation & Safety Checks**
    Folder imports validate the Google Drive URL, verify the folder is publicly shared ("Anyone with the link") and non-empty, and block duplicate imports of the same folder within an organization with a clear conflict message.

-   **Repository Tracking & Listing**
    Every imported Drive folder is tracked as a Repository per organization with sync status, timestamps, error messages, and resource counts, and can be viewed via a new paginated, org-scoped repository listing API.

---

## 🔄 Migration

-   **0083_repository**
    Creates the new `repositories` table to store external repository details (name, provider type, root link, sync status/tracking fields, resource counts) mapped to an organization.

-   **0084_mediaorgmapping**
    Creates the `MediaOrgMapping` table to map media entries to organizations (media ↔ org_id).

-   **0085_alter_mediaorgmapping_org_id**
    Changes the `org_id` column on `MediaOrgMapping` from BigInteger to Text to support non-numeric org identifiers.

-   **0086_repository_org_root_link_unique**
    Adds a unique constraint on `(org_id, root_link)` in the `repositories` table to prevent duplicate repository links per organization.

-   **0087_add_source_provider_to_media**
    Adds a nullable `source_provider` field to the `Media` model to record where the media originated (Google Drive, OneDrive, or Local).

---

## ⚙️ New Environment Variables

The following environment variables were added to configure the Google Drive OAuth integration, and Redis and the Celery workers used by the asynchronous import pipeline:

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `127.0.0.1` | Hostname of the Redis server used as the Celery broker and result backend. |
| `REDIS_PORT` | `6379` | Port of the Redis server. |
| `REDIS_USE_SSL` | `false` | Set to `true` to connect to Redis over SSL (`rediss://`). |
| `REDIS_CELERY_DB` | `2` | Redis database number used for the Celery broker and result backend. |
| `CELERY_TASK_DEFAULT_QUEUE` | `sg_commons_queue` | Default queue name that Celery tasks are published to and workers consume from. |
| `GOOGLE_DRIVE_SCOPES` | `https://www.googleapis.com/auth/drive.readonly` | Google OAuth scopes requested when connecting a Google Drive account. Defaults to read-only Drive access. |
---

👨‍💻 **Service:** Commons Backend
🏷️ **Version:** 1.0.0