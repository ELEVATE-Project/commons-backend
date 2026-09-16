#!/usr/bin/env python3
"""
Sync media files to vector database using Celery tasks (same as extraction logic).

This version uses the same Celery task approach as the normal extraction flow,
which avoids nginx size limits and handles large files better.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

# Django setup
import django
# if __name__ == '__main__':
#     project_root = Path(__file__).resolve().parent.parent.parent
#     sys.path.insert(0, str(project_root))
#     os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
#     django.setup()

from django.db.models import Q
from chatbot.models import Media, Company, CompanyBot
from chatbot.celery_tasks.knowledge_service.media_tasks import save_in_vector_db, update_in_vector_db
from celery.result import AsyncResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sync_media_to_vector_db_celery.log')
    ]
)
logger = logging.getLogger(__name__)


class MediaVectorDBSyncCelery:
    """Sync media files using Celery tasks (same as extraction logic)"""
    
    def __init__(
        self,
        company_slug: Optional[str] = None,
        company_bot_id: Optional[int] = None,
        media_ids: Optional[List[int]] = None,
        batch_size: int = 10,
        dry_run: bool = False,
        skip_errors: bool = True,
        task_timeout: int = 300,
        poll_interval: float = 2.0,
        update_mode: bool = False
    ):
        """
        Initialize sync manager using Celery tasks
        
        Args:
            company_slug: Filter by company slug
            company_bot_id: Filter by company bot ID
            media_ids: Specific media IDs to process
            batch_size: Number of media to process in each batch
            dry_run: Test mode (don't actually upsert)
            skip_errors: Continue processing if errors occur
            task_timeout: Maximum time to wait for each Celery task (seconds)
            poll_interval: How often to check task status (seconds)
            update_mode: Use update instead of upsert
        """
        self.company_slug = company_slug
        self.company_bot_id = company_bot_id
        self.media_ids = media_ids
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.skip_errors = skip_errors
        self.task_timeout = task_timeout
        self.poll_interval = poll_interval
        self.update_mode = update_mode
        
        self.stats = {
            'total_media': 0,
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'timeout': 0
        }
        
        self.results = []
        self._validate_filters()
    
    def _validate_filters(self):
        """Validate company and bot filters"""
        if self.company_slug:
            try:
                self.company = Company.objects.get(slug=self.company_slug)
                logger.info(f"Found company: {self.company.name} ({self.company_slug})")
                print(f"✅ Found company: {self.company.name} ({self.company_slug})")
            except Company.DoesNotExist:
                logger.error(f"Company with slug '{self.company_slug}' not found")
                raise ValueError(f"Company with slug '{self.company_slug}' not found")
        
        if self.company_bot_id:
            try:
                self.company_bot = CompanyBot.objects.get(id=self.company_bot_id)
                logger.info(f"Found bot: {self.company_bot.name} (ID: {self.company_bot_id})")
                print(f"✅ Found bot: {self.company_bot.name} (ID: {self.company_bot_id})")
            except CompanyBot.DoesNotExist:
                logger.error(f"CompanyBot with ID {self.company_bot_id} not found")
                raise ValueError(f"CompanyBot with ID {self.company_bot_id} not found")
    
    def get_media_queryset(self):
        """Get filtered media queryset"""
        queryset = Media.objects.all()
        
        # Apply filters
        if self.media_ids:
            queryset = queryset.filter(id__in=self.media_ids)
            print(f"🔍 Filter: Specific media IDs: {self.media_ids}")
        
        if self.company_slug:
            queryset = queryset.filter(
                Q(company_bot__company__slug=self.company_slug) |
                Q(organization__slug=self.company_slug)
            )
            print(f"🔍 Filter: Company slug = {self.company_slug}")
        
        if self.company_bot_id:
            queryset = queryset.filter(company_bot_id=self.company_bot_id)
            print(f"🔍 Filter: Bot ID = {self.company_bot_id}")
        
        # Order by ID for consistent processing
        queryset = queryset.order_by('id')
        
        self.stats['total_media'] = queryset.count()
        print(f"📊 Total media to process: {self.stats['total_media']}\n")
        
        return queryset
    
    def wait_for_task(self, task_result: AsyncResult, media_id: int) -> Dict[str, Any]:
        """
        Wait for Celery task to complete and return result
        
        Args:
            task_result: Celery AsyncResult object
            media_id: Media ID being processed
            
        Returns:
            Result dictionary
        """
        elapsed = 0
        while elapsed < self.task_timeout:
            if task_result.ready():
                try:
                    status_code = task_result.get(timeout=1)
                    
                    if 200 <= status_code < 300:
                        logger.info(f"Task completed successfully for media ID {media_id}: Status {status_code}")
                        return {
                            'success': True,
                            'media_id': media_id,
                            'status_code': status_code,
                            'message': 'Successfully processed via Celery',
                            'task_id': task_result.id
                        }
                    else:
                        logger.error(f"Task failed for media ID {media_id}: Status {status_code}")
                        return {
                            'success': False,
                            'media_id': media_id,
                            'status_code': status_code,
                            'message': f'Task failed with status {status_code}',
                            'task_id': task_result.id
                        }
                except Exception as e:
                    logger.error(f"Error getting task result for media ID {media_id}: {str(e)}")
                    return {
                        'success': False,
                        'media_id': media_id,
                        'message': f'Task error: {str(e)}',
                        'task_id': task_result.id
                    }
            
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval
        
        # Timeout
        logger.warning(f"Task timeout for media ID {media_id} after {self.task_timeout}s")
        return {
            'success': False,
            'media_id': media_id,
            'message': f'Task timeout after {self.task_timeout}s',
            'task_id': task_result.id,
            'timeout': True
        }
    
    def sync_single_media(self, media_id: int) -> Dict[str, Any]:
        """
        Sync a single media file using Celery task
        
        Args:
            media_id: Media ID to process
            
        Returns:
            Result dictionary
        """
        try:
            logger.info(f"Processing media ID {media_id} via Celery")
            
            # Get media info for logging
            try:
                media = Media.objects.get(id=media_id)
                file_name = media.file.name.split('/')[-1] if media.file else 'Unknown'
                
                # Get file size if available
                try:
                    file_size_bytes = media.file.size
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    logger.info(f"Media ID {media_id}: {file_name} ({file_size_mb:.2f} MB)")
                except:
                    file_size_mb = None
                    logger.info(f"Media ID {media_id}: {file_name}")
            except Media.DoesNotExist:
                logger.error(f"Media ID {media_id} not found")
                return {
                    'success': False,
                    'media_id': media_id,
                    'message': 'Media not found'
                }
            
            if self.dry_run:
                logger.info(f"DRY RUN: Would process media ID {media_id} via Celery")
                print(f"  🔍 DRY RUN: Would process media ID {media_id}")
                print(f"     File: {file_name}")
                if file_size_mb:
                    print(f"     Size: {file_size_mb:.2f} MB")
                print(f"     Method: Celery {'update' if self.update_mode else 'upsert'}")
                
                return {
                    'success': True,
                    'media_id': media_id,
                    'file_name': file_name,
                    'message': 'Dry run - not processed',
                    'dry_run': True
                }
            
            # Submit Celery task (same as extraction logic)
            if self.update_mode:
                task_result = update_in_vector_db.apply_async(
                    args=(media_id, self.company_slug),
                    countdown=0
                )
                logger.info(f"Submitted UPDATE task {task_result.id} for media ID {media_id}")
            else:
                task_result = save_in_vector_db.apply_async(
                    args=(media_id, self.company_slug),
                    countdown=0
                )
                logger.info(f"Submitted UPSERT task {task_result.id} for media ID {media_id}")
            
            print(f"  📤 Submitted Celery task {task_result.id}")
            print(f"     Waiting for completion (timeout: {self.task_timeout}s)...")
            
            # Wait for task to complete
            result = self.wait_for_task(task_result, media_id)
            
            if result['success']:
                print(f"  ✅ Successfully processed media ID {media_id}")
            elif result.get('timeout'):
                print(f"  ⏱️  Task timeout for media ID {media_id}")
            else:
                print(f"  ❌ Failed to process media ID {media_id}")
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Error processing media ID {media_id}: {error_msg}")
            print(f"  ❌ Error processing media ID {media_id}: {error_msg}")
            
            return {
                'success': False,
                'media_id': media_id,
                'message': error_msg
            }
    
    def sync_all(self) -> Dict[str, Any]:
        """Sync all filtered media using Celery tasks"""
        media_queryset = self.get_media_queryset()
        
        if self.stats['total_media'] == 0:
            logger.warning("No media found to process")
            print("⚠️  No media found to process!")
            return self.stats
        
        logger.info(f"Starting Celery-based Vector DB Sync - Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"{'='*80}")
        print(f"Starting Celery-based Vector DB Sync")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Method: {'UPDATE' if self.update_mode else 'UPSERT'}")
        print(f"Batch size: {self.batch_size}")
        print(f"Task timeout: {self.task_timeout}s")
        print(f"Poll interval: {self.poll_interval}s")
        print(f"{'='*80}\n")
        
        # Process in batches
        media_ids = list(media_queryset.values_list('id', flat=True))
        
        for i in range(0, len(media_ids), self.batch_size):
            batch = media_ids[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(media_ids) + self.batch_size - 1) // self.batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches}")
            print(f"\n{'='*80}")
            print(f"Batch {batch_num}/{total_batches} (Media IDs: {batch[0]} - {batch[-1]})")
            print(f"{'='*80}")
            
            for media_id in batch:
                self.stats['processed'] += 1
                progress = f"[{self.stats['processed']}/{self.stats['total_media']}]"
                
                print(f"\n{progress} Processing Media ID: {media_id}")
                print(f"{'-'*80}")
                
                result = self.sync_single_media(media_id)
                self.results.append(result)
                
                if result['success']:
                    self.stats['successful'] += 1
                elif result.get('timeout'):
                    self.stats['timeout'] += 1
                    self.stats['failed'] += 1
                else:
                    self.stats['failed'] += 1
                    
                    if not self.skip_errors:
                        logger.error("Stopping due to error (skip_errors=False)")
                        print(f"\n❌ Stopping due to error (skip_errors=False)")
                        self._print_summary()
                        return self.stats
        
        self._print_summary()
        return self.stats
    
    def _print_summary(self):
        """Print sync summary"""
        logger.info(f"Sync Summary - Total: {self.stats['total_media']}, Successful: {self.stats['successful']}, Failed: {self.stats['failed']}, Timeout: {self.stats['timeout']}")
        print(f"\n{'='*80}")
        print(f"SYNC SUMMARY (Celery Mode)")
        print(f"{'='*80}")
        print(f"Mode:               {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Method:             {'UPDATE' if self.update_mode else 'UPSERT'}")
        print(f"Total Media:        {self.stats['total_media']}")
        print(f"Processed:          {self.stats['processed']}")
        print(f"Successful:         {self.stats['successful']}")
        print(f"Failed:             {self.stats['failed']}")
        print(f"Timeout:            {self.stats['timeout']}")
        print(f"{'='*80}\n")
        
        if self.stats['failed'] > 0:
            logger.error(f"Failed media count: {self.stats['failed']}")
            print("Failed Media:")
            for result in self.results:
                if not result['success']:
                    media_id = result.get('media_id', 'Unknown')
                    message = result.get('message', 'Unknown error')
                    task_id = result.get('task_id', 'N/A')
                    logger.error(f"Failed media ID {media_id}: {message} (task: {task_id})")
                    print(f"  ❌ Media ID {media_id}: {message}")
                    print(f"     Task ID: {task_id}")
            print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Sync media files using Celery tasks (same as extraction logic)'
    )
    
    parser.add_argument('--company-slug', help='Filter by company slug')
    parser.add_argument('--bot-id', type=int, help='Filter by CompanyBot ID')
    parser.add_argument('--media-ids', help='Comma-separated list of media IDs')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size (default: 10)')
    parser.add_argument('--dry-run', action='store_true', help='Test mode')
    parser.add_argument('--stop-on-error', action='store_true', help='Stop on first error')
    parser.add_argument('--task-timeout', type=int, default=300, help='Task timeout in seconds (default: 300)')
    parser.add_argument('--poll-interval', type=float, default=2.0, help='Poll interval in seconds (default: 2.0)')
    parser.add_argument('--update', action='store_true', help='Use update instead of upsert')
    
    args = parser.parse_args()
    
    # Parse media IDs
    media_ids = None
    if args.media_ids:
        try:
            media_ids = [int(x.strip()) for x in args.media_ids.split(',')]
        except ValueError:
            print("❌ Error: Invalid media IDs format")
            sys.exit(1)
    
    try:
        syncer = MediaVectorDBSyncCelery(
            company_slug=args.company_slug,
            company_bot_id=args.bot_id,
            media_ids=media_ids,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            skip_errors=not args.stop_on_error,
            task_timeout=args.task_timeout,
            poll_interval=args.poll_interval,
            update_mode=args.update
        )
        
        stats = syncer.sync_all()
        
        exit_code = 0 if stats['failed'] == 0 else 1
        logger.info(f"Sync completed with exit code {exit_code}")
        sys.exit(exit_code)
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

#
# if __name__ == '__main__':
#     main()

# CALL FOR SOME MEDIA IDS ONLY
# syncer = MediaVectorDBSyncCelery(
#     company_slug=None,
#     media_ids=[364, 396],
# )
#
# syncer.sync_all()