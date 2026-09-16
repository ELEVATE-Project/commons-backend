import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

from chatbot.models import Media
from chatbot.celery_tasks.knowledge_service.media_tasks import generate_media_preview
from django.db.models import Q
import logging

logger = logging.getLogger('django')


def generate_thumbnails_for_media(company_slug=None, limit=None, media_ids=None, force=False):
    query = Q()

    if not force:
        query &= Q(thumbnail__isnull=True) | Q(thumbnail='')

    if company_slug:
        query &= Q(organization__slug=company_slug)

    if media_ids:
        query &= Q(id__in=media_ids)

    media_qs = Media.objects.filter(query).order_by('-created_at')

    if limit:
        media_qs = media_qs[:limit]

    total_count = media_qs.count()

    if total_count == 0:
        print("No media files found matching the criteria.")
        return

    print(f"Found {total_count} media file(s) to process.")
    print("-" * 60)

    success_count = 0
    error_count = 0
    skipped_count = 0

    for idx, media in enumerate(media_qs, 1):
        try:
            print(f"\n[{idx}/{total_count}] Processing Media ID: {media.id}")
            print(f"  Name: {media.name}")
            print(f"  Type: {media.media_type}")
            print(f"  File: {media.file.name if media.file else 'N/A'}")

            if not media.file:
                print("  ⚠️  Skipped: No file attached")
                skipped_count += 1
                continue

            task = generate_media_preview.apply_async(args=(media.id,), countdown=2)
            print(f"  ✅ Task queued: {task.id}")
            success_count += 1

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            error_count += 1
            logger.error(f"Error processing media {media.id}: {str(e)}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total processed: {total_count}")
    print(f"✅ Tasks queued: {success_count}")
    print(f"⚠️  Skipped: {skipped_count}")
    print(f"❌ Errors: {error_count}")
    print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate thumbnails for Media objects'
    )
    parser.add_argument(
        '--company-slug',
        type=str,
        help='Filter by company slug'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of media to process'
    )
    parser.add_argument(
        '--media-ids',
        type=str,
        help='Comma-separated list of media IDs to process'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Regenerate thumbnails even if they exist'
    )

    args, unknown = parser.parse_known_args()

    media_ids = None
    if args.media_ids:
        media_ids = [int(x.strip()) for x in args.media_ids.split(',')]

    print("=" * 60)
    print("THUMBNAIL GENERATION SCRIPT")
    print("=" * 60)

    if args.company_slug:
        print(f"Company: {args.company_slug}")
    if args.limit:
        print(f"Limit: {args.limit}")
    if media_ids:
        print(f"Media IDs: {media_ids}")
    if args.force:
        print("Mode: Force regeneration")

    print("=" * 60)

    if not media_ids or len(media_ids) > 10:
        response = input("\nProceed with thumbnail generation? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    generate_thumbnails_for_media(
        company_slug=args.company_slug,
        limit=args.limit,
        media_ids=media_ids,
        force=args.force
    )


def run(*args):
    sys.argv = ['generate_thumbnails.py'] + list(args)
    main()

#
# if __name__ == '__main__':
#     main()
