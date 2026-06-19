"""
Standalone Media to OpenAI Vector Store Uploader
All-in-one script that can be run directly or pasted into terminal
Requirements:
    - OPENAI_API_KEY must be set in environment
    - OPENAI_VECTOR_STORE_ID must be set in environment
    - Django must be properly configured
"""

import os
import sys
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

# Django setup
import django

from chatbot.celery_tasks.knowledge_service.media_tasks import prepare_vector_db_data

try:
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
except NameError:
    # __file__ is not defined in interactive shell, use cwd
    project_root = Path.cwd().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
django.setup()

from chatbot.models import Media, CompanyBot


# ============================================================================
# EXCEPTIONS
# ============================================================================

class OpenAIVectorStoreError(Exception):
    """Base exception for OpenAI vector store operations"""
    pass


class OpenAIUploadError(OpenAIVectorStoreError):
    """Exception raised when uploading file to OpenAI fails"""
    pass


class VectorStoreError(OpenAIVectorStoreError):
    """Exception raised when adding file to vector store fails"""
    pass


class InvalidMediaError(OpenAIVectorStoreError):
    """Exception raised when media object is invalid or missing required data"""
    pass


# ============================================================================
# OPENAI CLIENT
# ============================================================================

class OpenAIClient:
    """Client for interacting with OpenAI API"""

    OPENAI_FILES_URL = "https://api.openai.com/v1/files"
    OPENAI_VECTOR_STORE_FILES_URL = "https://api.openai.com/v1/vector_stores/{vector_store_id}/files"

    def __init__(self, api_key: Optional[str] = None, vector_store_id: Optional[str] = None, bot_route: Optional[str] = None):
        """Initialize OpenAI client"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        # Get vector store ID from CompanyBot if bot_route is provided
        if bot_route:
            self.vector_store_id = self._get_vector_store_id_from_bot(bot_route)
        else:
            self.vector_store_id = vector_store_id or os.getenv('OPENAI_VECTOR_STORE_ID')

        if not self.vector_store_id:
            raise ValueError(
                "OPENAI_VECTOR_STORE_ID not found. Either set environment variable or provide bot_route"
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "assistants=v2",
        }

    def _get_vector_store_id_from_bot(self, bot_route: str) -> Optional[str]:
        """Get vector store ID from CompanyBot's tool_context"""
        import json_repair

        try:
            company_bot = CompanyBot.objects.filter(route=bot_route).first()

            if not company_bot:
                raise ValueError(f"CompanyBot with route '{bot_route}' not found")

            logger.info(f"Found CompanyBot: {company_bot.name} (ID: {company_bot.id}, Route: {bot_route})")

            tool = company_bot.tool_context
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
                raise ValueError(
                    f"Vector store ID not found in tool_context for bot '{bot_route}' (ID: {company_bot.id})"
                )

            logger.info(f"Extracted Vector Store ID: {vector_store_id}")
            print(f"✅ Using Vector Store ID from bot '{bot_route}': {vector_store_id}")

            return vector_store_id

        except Exception as e:
            logger.error(f"Failed to get vector store ID from bot route '{bot_route}': {str(e)}")
            raise

    def add_file_to_vector_store(
            self,
            file_id: str,
            metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add uploaded file to vector store with metadata"""
        try:
            vector_store_url = self.OPENAI_VECTOR_STORE_FILES_URL.format(
                vector_store_id=self.vector_store_id
            )

            # Keep only specific fields
            ALLOWED_FIELDS = ['company', 'url', 'tags', 'TITLE', 'type', 'DOCUMENT TYPE']

            attributes = {}
            for k, v in metadata.items():
                if k in ALLOWED_FIELDS and v is not None:
                    # Stringify tags if it's a list
                    if k == 'tags' and isinstance(v, list):
                        attributes[str(k)] = ', '.join(str(tag) for tag in v)
                    else:
                        attributes[str(k)] = str(v)

            logger.info(f"Metadata: {len(attributes)} fields - {list(attributes.keys())}")

            payload = {
                "file_id": file_id,
                "attributes": attributes,
            }

            response = requests.post(
                vector_store_url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
                timeout=60
            )

            if not response.ok:
                error_body = response.text
                logger.error(f"OpenAI Error ({response.status_code}): {error_body}")
                response.raise_for_status()

            return response.json()

        except Exception as e:
            raise VectorStoreError(
                f"Failed to add file to vector store. File ID: {file_id}. "
                f"Error: {str(e)}"
            )


# ============================================================================
# UPLOADER
# ============================================================================

try:
    SCRIPT_DIR = Path(__file__).parent
except NameError:
    SCRIPT_DIR = Path.cwd()
LOG_FILE = SCRIPT_DIR / 'openai_vector_store_upload.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class MediaVectorStoreUploader:
    """Orchestrator for uploading all media files to OpenAI Vector Store"""

    def __init__(
        self,
        max_workers: int = 4,
        bot_route: Optional[str] = None,
        vector_store_id: Optional[str] = None,
        limit: Optional[int] = None,
        media_ids: Optional[List[int]] = None
    ):
        """
        Initialize uploader with OpenAI client

        Args:
            max_workers: Number of parallel workers
            bot_route: Route of CompanyBot to get vector store ID from (e.g., "/free-flow-bot")
            vector_store_id: Direct vector store ID (alternative to bot_route)
            limit: Number of media files to process (None = process all)
            media_ids: List of specific media IDs to process (None = process all)
        """
        self.client = OpenAIClient(bot_route=bot_route, vector_store_id=vector_store_id)
        self.max_workers = max_workers
        self.limit = limit
        self.media_ids = media_ids
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0
        }
        self.results = []

    def _get_media_info(self, media: Media) -> Dict[str, Any]:
        """Extract required information from media object using prepare_vector_db_data"""
        try:
            media_obj, file_name, file_content, metadata = prepare_vector_db_data(
                media_id=media.id,
                company_slug=None
            )

            organization = metadata.get('company')

            if not organization:
                raise InvalidMediaError(f"Media ID {media.id} has no organization in metadata")

            if not file_name:
                raise InvalidMediaError(f"Media ID {media.id} has no filename")

            if not file_content:
                raise InvalidMediaError(f"Media ID {media.id} has no file content")

            return {
                'organization': organization,
                'file_name': file_name,
                'file_content': file_content,
                'metadata': metadata
            }
        except Exception as e:
            raise InvalidMediaError(f"Failed to extract info from media ID {media.id}: {str(e)}")

    def _upload_single_media(self, media: Media) -> Tuple[int, bool, str, Dict[str, Any]]:
        """Upload a single media file to OpenAI vector store"""
        try:
            # Extract media information
            media_info = self._get_media_info(media)

            logger.info(
                f"Processing Media ID: {media.id}, Name: {media.name}, "
                f"Company: {media_info['organization']}, File: {media_info['file_name']}"
            )

            # Upload file content directly to OpenAI
            openai_response = requests.post(
                self.client.OPENAI_FILES_URL,
                headers=self.client.headers,
                files={
                    "file": (media_info['file_name'], media_info['file_content']),
                },
                data={
                    "purpose": "assistants",
                },
            )

            openai_response.raise_for_status()
            upload_response = openai_response.json()
            file_id = upload_response.get('id')

            if not file_id:
                raise OpenAIUploadError(f"No file_id returned from OpenAI for media {media.id}")

            # Add to vector store with metadata
            vector_store_response = self.client.add_file_to_vector_store(
                file_id=file_id,
                metadata=media_info['metadata']
            )

            result = {
                "success": True,
                "media_id": media.id,
                "media_name": media.name,
                "file_id": file_id,
                "company": media_info['organization'],
                "file_name": media_info['file_name']
            }

            success_msg = (
                f"[SUCCESS] Media ID: {media.id}, Name: {media.name}, "
                f"File ID: {file_id}, Company: {media_info['organization']}"
            )
            logger.info(success_msg)

            return (media.id, True, 'success', result)

        except InvalidMediaError as e:
            skip_msg = (
                f"[SKIPPED] Media ID: {media.id}, Name: {media.name}, "
                f"Reason: {str(e)}"
            )
            logger.warning(skip_msg)
            return (media.id, False, 'skipped', {
                "success": False,
                "media_id": media.id,
                "media_name": media.name,
                "error": str(e),
                "error_type": "skipped"
            })

        except OpenAIVectorStoreError as e:
            error_msg = (
                f"[FAILED] Media ID: {media.id}, Name: {media.name}, "
                f"Error: {str(e)}"
            )
            logger.error(error_msg)
            return (media.id, False, 'failed', {
                "success": False,
                "media_id": media.id,
                "media_name": media.name,
                "error": str(e),
                "error_type": "failed"
            })

        except Exception as e:
            error_msg = (
                f"[FAILED] Media ID: {media.id}, Name: {media.name}, "
                f"Unexpected error: {str(e)}"
            )
            logger.error(error_msg)
            return (media.id, False, 'failed', {
                "success": False,
                "media_id": media.id,
                "media_name": media.name,
                "error": str(e),
                "error_type": "failed"
            })

    def _upload_media_parallel(self, all_media):
        """Upload media files in parallel using ThreadPoolExecutor"""
        logger.info(f"Running with ThreadPoolExecutor (workers={self.max_workers})")
        print(f"[INFO] Running with ThreadPoolExecutor (workers={self.max_workers})")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            futures = [
                executor.submit(self._upload_single_media, media)
                for media in all_media
            ]

            # Process completed tasks
            completed = 0
            for future in as_completed(futures):
                completed += 1
                media_id, success, status, result = future.result()

                # Store result
                self.results.append(result)

                # Update stats based on status
                if status == 'success':
                    self.stats['successful'] += 1
                elif status == 'skipped':
                    self.stats['skipped'] += 1
                elif status == 'failed':
                    self.stats['failed'] += 1

                # Log progress
                if completed % 10 == 0 or completed == self.stats['total']:
                    logger.info(f"Progress: {completed}/{self.stats['total']} completed")
                    print(f"[INFO] Progress: {completed}/{self.stats['total']} completed")

    def run(self):
        """Main execution method - processes all media files"""
        start_time = datetime.now()

        logger.info("=" * 80)
        logger.info("Starting OpenAI Vector Store Upload Process")
        logger.info(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Vector Store ID: {self.client.vector_store_id}")
        if self.limit:
            logger.info(f"Limit: Processing only {self.limit} media file(s)")
        if self.media_ids:
            logger.info(f"Processing specific media IDs: {self.media_ids}")
        logger.info("=" * 80)

        # Query media from database
        if self.media_ids:
            # Filter by specific media IDs
            all_media = Media.objects.filter(id__in=self.media_ids)
            print(f"🔍 Processing specific media IDs: {self.media_ids}")
        else:
            # Get all media
            all_media = Media.objects.all()

        # Apply limit if specified (only if not using media_ids)
        if self.limit and not self.media_ids:
            all_media = all_media[:self.limit]
            print(f"⚠️  LIMIT ACTIVE: Processing only {self.limit} media file(s)")

        all_media = list(all_media)
        self.stats['total'] = len(all_media)

        logger.info(f"Total media files to process: {self.stats['total']}")
        logger.info("-" * 80)

        # Process media files in parallel
        self._upload_media_parallel(all_media)

        # Log final summary
        end_time = datetime.now()
        duration = end_time - start_time

        logger.info("=" * 80)
        logger.info("Upload Process Completed")
        logger.info(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration}")
        logger.info("")
        logger.info("SUMMARY:")
        logger.info(f"  Total Media Files: {self.stats['total']}")
        logger.info(f"  Successful Uploads: {self.stats['successful']}")
        logger.info(f"  Failed Uploads: {self.stats['failed']}")
        logger.info(f"  Skipped (Invalid): {self.stats['skipped']}")
        logger.info(f"  Success Rate: {(self.stats['successful'] / self.stats['total'] * 100):.2f}%"
                   if self.stats['total'] > 0 else "  Success Rate: N/A")
        logger.info("=" * 80)

        # Print failed media details
        if self.stats['failed'] > 0 or self.stats['skipped'] > 0:
            print("\n" + "=" * 80)
            print("FAILED/SKIPPED MEDIA:")
            print("=" * 80)
            for result in self.results:
                if not result.get('success', False):
                    print(f"  ❌ Media ID {result['media_id']}: {result['media_name']}")
                    print(f"     Error: {result['error']}")
                    print(f"     Type: {result['error_type']}")
                    print()

        print("\n" + "=" * 80)
        print(f"✅ Process completed! Check logs at: {LOG_FILE}")
        print("=" * 80)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main entry point"""
    try:
        # Can adjust max_workers here if needed
        uploader = MediaVectorStoreUploader(max_workers=4)
        uploader.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        print(f"❌ Fatal error occurred: {str(e)}")
        sys.exit(1)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

# Example 1: Test with 1 specific media file
# uploader = MediaVectorStoreUploader(
#     max_workers=4,
#     bot_route="/free-flow-bot",
#     media_ids=[340]
# )
# uploader.run()

# Example 2: Process multiple specific media files
# uploader = MediaVectorStoreUploader(
#     max_workers=4,
#     bot_route="/free-flow-bot",
#     media_ids=[704, 705, 706, 707, 708]
# )
# uploader.run()

# Example 3: Process all media files
# uploader = MediaVectorStoreUploader(
#     max_workers=4,
#     bot_route="/free-flow-bot"
# )
# uploader.run()

# Example 4: Test with first 5 media files using limit
# uploader = MediaVectorStoreUploader(
#     max_workers=4,
#     bot_route="/free-flow-bot",
#     limit=5
# )
# uploader.run()