import logging
from django.utils import timezone
from chatbot.scripts.guest_discussion.output.update_non_english_story import fix_guest_discussion_stories
from chatbot.scripts.mi_guest_flow.output.update_non_english_story import fix_guest_mi_story_stories
import os

logger = logging.getLogger('django')


def handle_non_english_fix_cron():
    """
    Cron job to fix non-English content in Guest Discussion and Guest MI Story flows.
    """
    try:
        logger.info('=' * 70)
        logger.info('🌐 Starting Non-English Content Fix Cron at: {}'.format(timezone.now()))
        print(f"Cron running from cwd: {os.getcwd()}")
        logger.info(f"Cron running from cwd: {os.getcwd()}")

        logger.info('🔧 Starting Guest Discussion non-English fix...')
        discussion_result = fix_guest_discussion_stories()
        logger.info(f"Guest Discussion CRON Fix Complete")

        # Fix Guest MI Story stories
        logger.info('🔧 Starting Guest MI Story non-English fix...')
        mi_story_result = fix_guest_mi_story_stories()
        logger.info(f"Guest MI Story CRON Fix Complete")

        logger.info('=' * 70)

        logger.info('Non-English Content Fix Cron completed successfully at: {}'.format(timezone.now()))

    except Exception as e:
        logger.exception("❌ Error during non-English content fix cron: %s", str(e))
