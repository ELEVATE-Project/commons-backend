import logging
from django.utils import timezone
from datetime import datetime, timedelta
import pytz
import ast
from django.db import connection
from chatbot.models import CompanyBot
from chatbot.scripts.guest_discussion.clean_story_script import get_story_count, clean_specific_stories
from chatbot.scripts.guest_discussion.post_processing.village_data_cleaning import run_for_specific_stories
# from chatbot.scripts.guest_discussion.translate_script import get_translate_story_count, translate_specific_story_ids
from chatbot.models import Story
import json

logger = logging.getLogger('django')


def handle_story_cleanup_cron():
    try:
        logger.info('🧹 Starting story cleanup cron at: {}'.format(timezone.now()))
        ist = pytz.timezone("Asia/Kolkata")
        yesterday = datetime.now().astimezone(ist) - timedelta(days=1)
        start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
        logger.info(f"⏱ Using start_time: {start_time.isoformat()}")
        logger.info(f"⏱ Using end_time:   {end_time.isoformat()}")

        story_ids = get_story_count(start_time=start_time, end_time=end_time)
        clean_specific_stories(story_ids=story_ids)
        logger.info('✅ Story cleanup cron completed at: {}'.format(timezone.now()))
        # logger.info('🚀 Starting translation immediately after cleanup...')
        # story_ids = get_translate_story_count(start_time=start_time, end_time=end_time)
        # translate_specific_story_ids(story_ids=story_ids)
        # logger.info('✅ Story translation (chained) completed at: {}'.format(timezone.now()))

    except Exception as e:
        logger.exception("❌ Error during story cleanup/translation cron: %s", str(e))


def handle_village_ingestion_cron():
    try:
        logger.info('🧹 Starting village ingestion cron at: %s', timezone.now())

        bot = CompanyBot.objects.filter(route='/script_village_mapping').first()
        master_villages = json.loads(bot.end_context)

        result = list(Story.objects.filter(
            other_params__flow='guest-discussion'
        ).exclude(
            other_params__village__isnull= False  
        ).values('id'))


        logger.info(f"📄 Raw story data: {result}")

        story_ids = []

        try:
            if isinstance(result, str):
                story_dicts = ast.literal_eval(result)
            else:
                story_dicts = result

            for entry in story_dicts:
                if isinstance(entry, dict) and 'id' in entry:
                    story_ids.append(entry['id'])
                elif isinstance(entry, (str, int)):
                    story_ids.append(entry)

        except Exception as parse_err:
            logger.exception("❌ Failed to parse SQL result: %s", str(parse_err))
            return

        if not story_ids:
            logger.warning("⚠️ No story IDs found from SQL. Skipping village mapping.")
            return

        summary = run_for_specific_stories(story_ids=story_ids, master_villages = master_villages)
        logger.info(f'✅ Village summary: {summary}')
        logger.info('🎉 Completed village ingestion at: %s', timezone.now())

    except Exception as e:
        logger.exception("❌ Error during village ingestion cron: %s", str(e))
