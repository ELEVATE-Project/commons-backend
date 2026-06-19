import json
import os
from chatbot.models import Story, ChatSession, CompanyChat, CompanyBot, Theme, ThemeType
from jinja2 import Template
import json_repair
import logging
from django.utils.timezone import make_aware
from datetime import datetime
from retrying import retry
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from chatbot.llm_models.llm_script import handle_bedrock_model

from chatbot.utils.chat_utils import format_message_as_per_bedrock_format

logger = logging.getLogger('django')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


# ===== KEY CHANGES IMPLEMENTED =====
# CHANGE 1: Theme master list from file - see get_master_themes_list() function
#           - Single source of truth for themes
#           - Creates file with defaults if not exists
#           - Updates file when new themes discovered
#
# CHANGE 2: Uses CompanyBot route='/chaupal-theme-script' - see extract_themes_for_story()
#           - Gets prompt from CompanyBot.context
#           - Gets tools from CompanyBot.tool_context
#
# CHANGE 3: Session type filtering - see extract_themes_for_all_stories(), extract_themes_batch(), etc.
#           - session_type parameter in all major functions
#           - Default: ChatSession.objects.all() when session_type=None
#           - Filtered: ChatSession.objects.filter(session_type=X) when specified
# ===================================


def get_master_themes_list_for_bot(company_bot):
    """Get the master list of themes from Theme model for a specific bot"""
    try:
        theme_obj = Theme.objects.filter(bot=company_bot).first()

        if not theme_obj:
            logger.info(f"No themes found for bot {company_bot.name}, returning empty list")
            return []

        # Check if bot uses master theme
        if theme_obj.theme_type == ThemeType.MASTER and theme_obj.master_theme:
            # Use themes from the master theme
            master_theme_obj = theme_obj.master_theme
            logger.info(f"Bot {company_bot.name} uses master theme from bot {master_theme_obj.bot.name}")
            return master_theme_obj.themes if master_theme_obj.themes else []
        else:
            # Use bot's own custom themes
            logger.info(f"Bot {company_bot.name} uses custom themes - loaded {len(theme_obj.themes)} themes")
            return theme_obj.themes if theme_obj.themes else []

    except Exception as e:
        logger.error(f"Error loading themes for bot {company_bot.name}: {str(e)}")
        return []


def save_themes_for_bot(themes, company_bot):
    """Save themes to Theme model for a specific bot"""
    try:
        theme_obj, created = Theme.objects.get_or_create(
            bot=company_bot,
            defaults={'themes': themes, 'theme_type': ThemeType.CUSTOM}
        )

        if not created:
            # Check if bot uses master theme
            if theme_obj.theme_type == ThemeType.MASTER and theme_obj.master_theme:
                # Update the master theme instead
                master_theme_obj = theme_obj.master_theme
                master_theme_obj.themes = themes
                master_theme_obj.save()
                logger.info(f"Updated master theme (bot: {master_theme_obj.bot.name}) with {len(themes)} themes")
            else:
                # Update bot's custom themes
                theme_obj.themes = themes
                theme_obj.save()
                logger.info(f"Updated custom themes for bot {company_bot.name} with {len(themes)} themes")
        else:
            logger.info(f"Created new theme record for bot {company_bot.name} with {len(themes)} themes")

        return True

    except Exception as e:
        logger.error(f"Error saving themes for bot {company_bot.name}: {str(e)}")
        return False


def update_master_themes_list_for_bot(new_themes, company_bot):
    """Update the master themes list with new themes for a specific bot"""
    try:
        theme_obj = Theme.objects.filter(bot=company_bot).first()

        if not theme_obj:
            # Create new theme object with these themes
            logger.info(f"Creating new theme object for bot {company_bot.name}")
            return save_themes_for_bot(new_themes, company_bot)

        # Get current themes (considering master theme)
        current_themes = set(get_master_themes_list_for_bot(company_bot))
        new_unique_themes = set(new_themes) - current_themes

        if new_unique_themes:
            logger.info(f"New themes discovered for bot {company_bot.name}: {new_unique_themes}")

            # Determine which theme object to update
            if theme_obj.theme_type == ThemeType.MASTER and theme_obj.master_theme:
                # Update the master theme
                target_theme_obj = theme_obj.master_theme
                logger.info(f"Updating master theme (bot: {target_theme_obj.bot.name})")
            else:
                # Update bot's custom themes
                target_theme_obj = theme_obj
                logger.info(f"Updating custom themes for bot {company_bot.name}")

            # Update and save the themes
            updated_themes = sorted(list(current_themes.union(new_unique_themes)))
            target_theme_obj.themes = updated_themes
            target_theme_obj.save()

            logger.info(f"Added {len(new_unique_themes)} new themes")

        return list(new_unique_themes)

    except Exception as e:
        logger.error(f"Error updating themes for bot {company_bot.name}: {str(e)}")
        return []


def extract_themes_for_story(story):
    """Extract themes from a story using LLM"""
    try:
        # Initialize other_params if it doesn't exist
        if not story.other_params:
            story.other_params = {}

        # Check if story already has themes (for logging purposes)
        has_existing_themes = 'themes' in story.other_params and story.other_params['themes']
        if has_existing_themes:
            logger.info(f"Story ID {story.id} has existing themes: {story.other_params['themes']} - will re-extract")

        # Get the bot from the story's session
        session = ChatSession.objects.get(session=story.session)
        if not session.company_bot:
            logger.error(f"No company_bot found for session {story.session}")
            return f"❌ No company_bot found for session {story.session}"

        # Use the session's company_bot for theme extraction
        company_bot = session.company_bot
        theme_bot = CompanyBot.objects.filter(route='/chaupal-theme-script').first()
        logger.info(f"Using CompanyBot: {company_bot.name} (route: {company_bot.route}) and theme bot {theme_bot.name}")

        # Get master themes list for this specific bot (handles both custom and master themes)
        master_themes = get_master_themes_list_for_bot(company_bot)

        # Get theme extraction prompt from company bot context
        if theme_bot.context:
            # Render Jinja2 template with themes variable
            template = Template(theme_bot.context)
            prompt = template.render(themes=master_themes)
            logger.info(f"Using prompt from CompanyBot context with Jinja2 template rendering")
        else:
            # Fallback prompt if company bot has no context
            prompt = get_theme_extraction_prompt(master_themes)
            logger.info(f"Using fallback prompt as CompanyBot context is empty")

        # Get chat history
        company_chats = CompanyChat.objects.filter(session=story.session).order_by('created_at')

        messages = format_message_as_per_bedrock_format(chats=company_chats)
        formatted_prompt = [{"text": prompt}]

        # Get tools configuration from company bot or use default
        if theme_bot.tool_context:
            try:
                tools = json.loads(theme_bot.tool_context)
                logger.info("Using tools from CompanyBot tool_context")
            except:
                tools = get_theme_extraction_tools()
                logger.info("Using default tools due to invalid tool_context")
        else:
            tools = get_theme_extraction_tools()
            logger.info("Using default tools as CompanyBot has no tool_context")

        # Call LLM to extract themes
        response = handle_bedrock_model(
            system_prompt=formatted_prompt,
            messages=messages,
            model_name=theme_bot.llm_model,
            temperature=theme_bot.bot_temperature,
            max_token=theme_bot.max_token,
            company_bot=theme_bot,
            tools=tools
        )

        logger.info(f"LLM response for Story ID {story.id}: {response}")
        result = get_clean_output(response=response)
        logger.info(f"Cleaned result: {result}")

        if result and isinstance(result, str):
            result = json_repair.repair_json(result, return_objects=True)

        # Extract themes from result
        if result and isinstance(result, dict):
            domain_themes = result.get('domain_themes', [])
            issue_themes = result.get('issue_themes', [])

            if domain_themes or issue_themes:
                # Update master themes list with any new themes found for this bot
                all_themes = domain_themes + issue_themes
                new_themes = update_master_themes_list_for_bot(all_themes, company_bot)
                if new_themes:
                    logger.info(f"Story ID {story.id} introduced new themes: {new_themes}")

                # Save both types of themes to story
                story.other_params['themes'] = {
                    'domain_themes': domain_themes,
                    'issue_themes': issue_themes,
                }
                story.save(update_fields=["other_params"])

                if has_existing_themes:
                    logger.info(f"✅ Re-extracted themes for Story ID {story.id}: Domain: {domain_themes}, Issues: {issue_themes}")
                    return f"✅ Re-extracted themes for Story ID {story.id}: Domain: {domain_themes}, Issues: {issue_themes}"
                else:
                    logger.info(f"✅ Extracted themes for Story ID {story.id}: Domain: {domain_themes}, Issues: {issue_themes}")
                    return f"✅ Extracted themes for Story ID {story.id}: Domain: {domain_themes}, Issues: {issue_themes}"
            else:
                logger.error(f"No themes extracted for Story ID {story.id}")
                return f"⚠️ No themes extracted for Story ID {story.id}"
        else:
            logger.error(f"Invalid response format for Story ID {story.id}")
            return f"❌ Invalid response format for Story ID {story.id}"

    except ChatSession.DoesNotExist:
        logger.error(f"ChatSession not found for story session: {story.session}")
        return f"❌ ChatSession not found for story session: {story.session}"
    except Exception as e:
        logger.error(f"❌ Error extracting themes for Story ID {story.id}: {str(e)}")
        return f"❌ Error extracting themes for Story ID {story.id}: {str(e)}"


def get_theme_extraction_prompt(master_themes=None):
    """Get prompt for theme extraction with master themes list"""

    # Format master themes for the prompt
    if master_themes:
        themes_list = "\n".join(f"    - {theme}" for theme in master_themes)
        prompt = f"""
You are an AI assistant that extracts themes from educational discussions.

Based on the conversation, identify the main themes/topics being discussed. 

Here is our master list of themes. Try to map the discussion topics to these existing themes when possible:
{themes_list}

If you identify a theme that is clearly discussed but not in the above list, you can add it as a new theme.

Important instructions:
1. Only extract themes that are CLEARLY discussed in the conversation
2. Use the exact theme names from the master list when they match
3. If a topic is discussed that doesn't match any existing theme, create a new specific theme name
4. Be accurate and specific - don't assign themes that aren't actually discussed
5. Return between 1-5 themes that best represent the core topics
6. Themes should be in lowercase

Return the themes as a list of strings.
"""
    else:
        # Fallback prompt if no master themes
        prompt = """
You are an AI assistant that extracts themes from educational discussions.

Based on the conversation, identify the main themes/topics being discussed.

Extract themes that best represent the core topics discussed in the conversation.
Return only the themes that are clearly discussed.
There can be one or multiple themes. Be specific and accurate.
Themes should be in lowercase.
"""

    return prompt


def get_theme_extraction_tools():
    """Get tools configuration for theme extraction with both domain and issue themes"""
    tools = {
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": "extract_themes",
                        "description": "Extract domain themes and issue themes from the discussion",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "domain_themes": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Broad domain/sector themes (1-3 words each)"
                                    },
                                    "issue_themes": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Specific issue/challenge themes (2-5 words each)"
                                    }
                                },
                                "required": ["domain_themes", "issue_themes"]
                            }
                        }
                    }
                }
            ]
        }
    }

    return tools


def extract_themes_for_all_stories(start=0, end=None, session_type=None):
    """Extract themes for all stories

    Args:
        start: Starting index
        end: Ending index (None for all remaining)
        session_type: ChatType to filter sessions (None for all types)
    """
    # CHANGE 3: Use session_type parameter to filter, default to all if None
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        session_type_name = f"ChatType.{session_type}" if hasattr(session_type, 'name') else str(session_type)
        logger.info(f"Filtering by session type: {session_type_name}")
    else:
        session_ids = list(
            ChatSession.objects.all()
            .values_list('session', flat=True)
        )
        session_type_name = "ALL session types"
        logger.info("Processing ALL session types")

    stories_query = Story.objects.filter(session__in=session_ids).order_by('-id')

    if end:
        stories = stories_query[start:end]
    else:
        stories = stories_query[start:]

    total_count = stories.count()
    print(f"\n{'=' * 60}")
    print(f"Processing stories from {start} to {end if end else 'end'}... Total: {total_count}")
    print(f"Session type: {session_type_name}")
    print(f"{'=' * 60}\n")
    logger.info(
        f"Processing stories from {start} to {end if end else 'end'}... Total: {total_count}, Type: {session_type_name}")

    results = {
        'success': 0,
        'failed': 0,
        'already_has_themes': 0
    }

    for idx, story in enumerate(stories, 1):
        print(f"[{idx}/{total_count}] Processing Story ID: {story.id}")

        result = extract_themes_for_story(story)
        print(f"    {result}")

        if "✅" in result:
            results['success'] += 1
        elif "🟡" in result:
            results['already_has_themes'] += 1
        else:
            results['failed'] += 1

        # Optional progress update every 10 stories
        if idx % 10 == 0:
            print(f"\n--- Progress: {idx}/{total_count} stories processed ---")
            print(
                f"    Success: {results['success']}, Already has themes: {results['already_has_themes']}, Failed: {results['failed']}\n")

    print(f"\n{'=' * 60}")
    summary = f"Theme extraction completed:\n"
    summary += f"  - Successfully extracted: {results['success']}\n"
    summary += f"  - Already had themes: {results['already_has_themes']}\n"
    summary += f"  - Failed: {results['failed']}\n"
    summary += f"  - Total processed: {total_count}"
    print(summary)
    print(f"{'=' * 60}\n")
    logger.info(summary)
    return results


def extract_themes_batch(batch_size=100, session_type=None):
    """Process stories in batches

    Args:
        batch_size: Number of stories per batch
        session_type: ChatType to filter sessions (None for all types)
    """
    # CHANGE 3: Use session_type parameter to filter, default to all if None
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        session_type_name = f"ChatType.{session_type}" if hasattr(session_type, 'name') else str(session_type)
        logger.info(f"Batch processing for session type: {session_type_name}")
    else:
        session_ids = list(
            ChatSession.objects.all()
            .values_list('session', flat=True)
        )
        session_type_name = "ALL session types"
        logger.info("Batch processing for ALL session types")

    total_stories = Story.objects.filter(session__in=session_ids).count()
    print(f"\n{'=' * 60}")
    print(f"Total stories to process: {total_stories}")
    print(f"Session type: {session_type_name}")
    print(f"Batch size: {batch_size}")
    print(f"{'=' * 60}\n")

    processed = 0
    overall_results = {
        'success': 0,
        'failed': 0,
        'already_has_themes': 0
    }

    batch_num = 1
    while processed < total_stories:
        print(f"\n🔄 Processing batch {batch_num}: stories {processed} to {min(processed + batch_size, total_stories)}")

        batch_results = extract_themes_for_all_stories(
            start=processed,
            end=processed + batch_size,
            session_type=session_type
        )

        # Aggregate results
        overall_results['success'] += batch_results['success']
        overall_results['failed'] += batch_results['failed']
        overall_results['already_has_themes'] += batch_results['already_has_themes']

        processed += batch_size
        batch_num += 1

        # Optional: Add a small delay between batches
        import time
        time.sleep(2)

    print(f"\n{'=' * 60}")
    print("FINAL SUMMARY:")
    print(f"  - Total stories processed: {total_stories}")
    print(f"  - Successfully extracted: {overall_results['success']}")
    print(f"  - Already had themes: {overall_results['already_has_themes']}")
    print(f"  - Failed: {overall_results['failed']}")
    print(f"{'=' * 60}\n")

    return overall_results


def get_stories_by_date_range(start_time=None, end_time=None, session_type=None):
    """Get story IDs for a specific time range

    Args:
        start_time: Start datetime (default: 2025-01-01)
        end_time: End datetime (default: now)
        session_type: ChatType to filter sessions (None for all types)
    """
    if not start_time:
        start_time = make_aware(datetime(2025, 1, 1, 0, 0))
    if not end_time:
        end_time = make_aware(datetime.now())

    # CHANGE 3: Filter by session type if provided, otherwise get all
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(
                session_type=session_type,
                created_at__gte=start_time,
                created_at__lte=end_time
            )
            .order_by('created_at')
            .values_list('session', flat=True)
        )
        session_type_name = f"ChatType.{session_type}" if hasattr(session_type, 'name') else str(session_type)
    else:
        session_ids = list(
            ChatSession.objects.filter(
                created_at__gte=start_time,
                created_at__lte=end_time
            )
            .order_by('created_at')
            .values_list('session', flat=True)
        )
        session_type_name = "ALL session types"

    if session_ids:
        logger.info(f"Found {len(session_ids)} sessions ({session_type_name}) between {start_time} and {end_time}")
        print(f"Found {len(session_ids)} sessions ({session_type_name})")
    else:
        print(f"No sessions found in the given date range for {session_type_name}.")
        return []

    story_ids = list(
        Story.objects.filter(session__in=session_ids)
        .order_by('-id')
        .values_list('id', flat=True)
    )

    logger.info(f"Total stories in date range: {len(story_ids)}")
    print(f"Total stories: {len(story_ids)}")
    return story_ids


def extract_themes_for_specific_stories(story_ids):
    """Extract themes for specific stories by their IDs"""
    stories = Story.objects.filter(id__in=story_ids)

    print(f"\n{'=' * 60}")
    print(f"Processing {stories.count()} specific stories for theme extraction...")
    print(f"{'=' * 60}\n")
    logger.info(f"Processing {stories.count()} stories for theme extraction...")

    results = {
        'success': 0,
        'failed': 0,
        'already_has_themes': 0
    }

    for idx, story in enumerate(stories, 1):
        print(f"[{idx}/{stories.count()}] Processing Story ID: {story.id}")

        result = extract_themes_for_story(story)
        print(f"    {result}")

        if "✅" in result:
            results['success'] += 1
        elif "🟡" in result:
            results['already_has_themes'] += 1
        else:
            results['failed'] += 1

    print(f"\n{'=' * 60}")
    summary = f"Theme extraction completed:\n"
    summary += f"  - Successfully extracted: {results['success']}\n"
    summary += f"  - Already had themes: {results['already_has_themes']}\n"
    summary += f"  - Failed: {results['failed']}\n"
    summary += f"  - Total processed: {stories.count()}"
    print(summary)
    print(f"{'=' * 60}\n")
    logger.info(summary)
    return results


def view_story_themes(story_id):
    """View themes for a specific story"""
    try:
        story = Story.objects.get(id=story_id)
        themes = story.other_params.get('themes', []) if story.other_params else []

        print(f"\nStory ID: {story_id}")
        print(f"Title: {story.title}")

        # Handle new format (dict)
        if isinstance(themes, dict):
            print(f"Domain Themes: {themes.get('domain_themes', [])}")
            print(f"Issue Themes: {themes.get('issue_themes', [])}")
        # Handle old format (list)
        else:
            print(f"Themes: {themes if themes else 'No themes found'}")

        return themes
    except Story.DoesNotExist:
        print(f"Story with ID {story_id} not found")
        return None


def view_master_themes_by_bot(company_bot=None):
    """View the current master themes list from Theme model"""
    try:
        if company_bot:
            # View themes for specific bot
            theme_obj = Theme.objects.filter(bot=company_bot).first()

            if not theme_obj:
                print(f"No themes found for bot: {company_bot.name}")
                return []

            master_themes = get_master_themes_list_for_bot(company_bot)

            print(f"\n{'=' * 60}")
            print(f"THEMES for bot: {company_bot.name}")
            print(f"Theme Type: {theme_obj.get_theme_type_display()}")
            if theme_obj.theme_type == ThemeType.MASTER and theme_obj.master_theme:
                print(f"Using master theme from: {theme_obj.master_theme.bot.name}")
            print(f"{'=' * 60}")
            print(f"Total themes: {len(master_themes)}")
            print(f"\nThemes (alphabetically sorted):")
            print(f"{'-' * 60}")

            for i, theme in enumerate(sorted(master_themes), 1):
                print(f"{i:3}. {theme}")

            print(f"{'=' * 60}\n")

            return master_themes
        else:
            # View themes for all bots
            all_theme_objs = Theme.objects.select_related('bot', 'master_theme__bot').all()

            print(f"\n{'=' * 60}")
            print(f"ALL BOT THEMES")
            print(f"{'=' * 60}")

            for theme_obj in all_theme_objs:
                print(f"\nBot: {theme_obj.bot.name} (ID: {theme_obj.bot.id})")
                print(f"Theme Type: {theme_obj.get_theme_type_display()}")

                if theme_obj.theme_type == ThemeType.MASTER and theme_obj.master_theme:
                    print(f"Using master theme from: {theme_obj.master_theme.bot.name}")
                    themes = theme_obj.master_theme.themes
                else:
                    themes = theme_obj.themes

                print(f"Total themes: {len(themes)}")
                print(f"Themes: {', '.join(sorted(themes[:10]))}")
                if len(themes) > 10:
                    print(f"... and {len(themes) - 10} more")
                print(f"{'-' * 40}")

            print(f"{'=' * 60}\n")

            return all_theme_objs

    except Exception as e:
        print(f"Error viewing master themes: {str(e)}")
        return []


def export_bot_themes_to_file(company_bot, filename=None):
    """Export a specific bot's themes to a JSON file"""
    try:
        if not filename:
            filename = f"themes_export_{company_bot.id}_{company_bot.name.replace(' ', '_')}.json"

        master_themes = get_master_themes_list_for_bot(company_bot)

        # Get theme statistics for this bot
        theme_stats = {}
        stories_with_bot = Story.objects.filter(
            session__in=ChatSession.objects.filter(company_bot=company_bot).values_list('session', flat=True)
        )

        for story in stories_with_bot:
            if story.other_params and 'themes' in story.other_params:
                themes = story.other_params.get('themes', {})
                if isinstance(themes, dict):
                    for theme in themes.get('all_themes', []):
                        theme_stats[theme] = theme_stats.get(theme, 0) + 1

        export_data = {
            "bot_id": company_bot.id,
            "bot_name": company_bot.name,
            "bot_route": company_bot.route,
            "themes": master_themes,
            "theme_count": len(master_themes),
            "theme_statistics": theme_stats,
            "export_date": datetime.now().isoformat()
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(master_themes)} themes for bot {company_bot.name} to {filename}")
        return filename

    except Exception as e:
        logger.error(f"Error exporting themes: {str(e)}")
        print(f"❌ Error exporting themes: {str(e)}")
        return None


def view_theme_statistics():
    """View statistics about themes usage across all stories"""
    try:
        theme_count = {}
        domain_theme_count = {}
        issue_theme_count = {}
        total_stories_with_themes = 0

        # Get all stories with themes
        stories_with_themes = Story.objects.filter(
            other_params__themes__isnull=False
        ).exclude(
            other_params__themes=[]
        )

        # Count theme occurrences
        for story in stories_with_themes:
            if story.other_params and 'themes' in story.other_params:
                themes = story.other_params.get('themes', [])

                # Handle new format (dict with domain_themes and issue_themes)
                if isinstance(themes, dict):
                    total_stories_with_themes += 1

                    # Count domain themes
                    for theme in themes.get('domain_themes', []):
                        domain_theme_count[theme] = domain_theme_count.get(theme, 0) + 1
                        theme_count[theme] = theme_count.get(theme, 0) + 1

                    # Count issue themes
                    for theme in themes.get('issue_themes', []):
                        issue_theme_count[theme] = issue_theme_count.get(theme, 0) + 1
                        theme_count[theme] = theme_count.get(theme, 0) + 1

                # Handle old format (list)
                elif isinstance(themes, list) and themes:
                    total_stories_with_themes += 1
                    for theme in themes:
                        theme_count[theme] = theme_count.get(theme, 0) + 1

        # Sort themes by count
        sorted_all_themes = sorted(theme_count.items(), key=lambda x: x[1], reverse=True)
        sorted_domain_themes = sorted(domain_theme_count.items(), key=lambda x: x[1], reverse=True)
        sorted_issue_themes = sorted(issue_theme_count.items(), key=lambda x: x[1], reverse=True)

        print(f"\n{'=' * 60}")
        print(f"THEME STATISTICS")
        print(f"{'=' * 60}")
        print(f"Total stories with themes: {total_stories_with_themes}")
        print(f"Total unique themes (all): {len(theme_count)}")
        print(f"Total unique domain themes: {len(domain_theme_count)}")
        print(f"Total unique issue themes: {len(issue_theme_count)}")

        # Show all themes
        print(f"\nAll themes (sorted by frequency):")
        print(f"{'Theme':<40} {'Count':<10} {'Percentage':<10}")
        print(f"{'-' * 60}")
        for theme, count in sorted_all_themes[:20]:  # Show top 20
            percentage = (count / total_stories_with_themes * 100) if total_stories_with_themes > 0 else 0
            print(f"{theme:<40} {count:<10} {percentage:.1f}%")

        print(f"{'=' * 60}\n")

        return sorted_all_themes

    except Exception as e:
        logger.error(f"Error viewing theme statistics: {str(e)}")
        print(f"Error viewing theme statistics: {str(e)}")
        return []


def retry_if_result_none(result):
    return result is None


def get_clean_output(response):
    """Clean and format the LLM response"""
    if response and isinstance(response, dict):
        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    if isinstance(response_json_content, dict) and response_json_content.get("type"):
        if "value" in response_json_content:
            value = response_json_content.get("value")
        elif "parameters" in response_json_content:
            value = response_json_content.get("parameters")
        else:
            value = None
        if value and isinstance(value, str) and value.strip():
            value = json_repair.repair_json(value, return_objects=True)
            response_json_content = value
        else:
            response_json_content = {}

    return response_json_content

# =============================================================================
# USAGE INSTRUCTIONS
# =============================================================================
#
# SETUP: The script will create master_themes.json automatically on first run
#        with default themes. You can also create it manually:
# {
#   "themes": ["education", "health", "agriculture", ...],
#   "last_updated": "2025-01-17T...",
#   "total_themes": 30
# }
#
# 1. Extract themes for ALL stories (all session types):
#    extract_themes_for_all_stories()
#
# 2. Extract themes for specific session type:
#    extract_themes_for_all_stories(session_type=ChatType.shikshaChaupal)
#
# 3. Process in batches (recommended for large datasets):
#    extract_themes_batch(batch_size=100)
#    extract_themes_batch(batch_size=100, session_type=ChatType.shikshaChaupal)
#
# 4. Extract themes for a specific date range:
#    from datetime import datetime
#    from django.utils.timezone import make_aware
#
#    start = make_aware(datetime(2025, 7, 25))
#    end = make_aware(datetime(2025, 8, 31))
#    story_ids = get_stories_by_date_range(start, end, 'normal')
#    extract_themes_for_specific_stories(story_ids)
#
#    # For specific session type:
#    story_ids = get_stories_by_date_range(start, end, session_type=ChatType.shikshaChaupal)
#    extract_themes_for_specific_stories(story_ids)
#
# 5. Extract themes for a specific range of stories:
#    extract_themes_for_all_stories(start=0, end=100)
#    extract_themes_for_all_stories(start=0, end=100, session_type=ChatType.shikshaChaupal)
#
# 6. View themes for a specific story:
#    view_story_themes(story_id=12345)
#
# 7. Extract themes for specific story IDs:
#    story_ids = [123, 456, 789]
#    extract_themes_for_specific_stories(story_ids)
#
# 8. View current master themes list (from file):
#    view_master_themes()
#
# 9. View theme statistics:
#    view_theme_statistics()
#
# 10. Export master themes to file:
#     export_master_themes_to_file("my_themes_export.json")
#
# 11. Manually save themes to file:
#     themes = ["education", "health", "agriculture"]
#     save_themes_to_file(themes, "custom_themes.json")
#
# 12. Add new themes to master list:
#     new_themes = ["disaster management", "mental health"]
#     add_new_themes_to_master_list(new_themes)
#
# IMPORTANT NOTES:
# - The script uses CompanyBot with route='/chaupal-theme-script' for theme extraction
# - Master themes are automatically updated when new themes are discovered
# - Session type defaults to ALL types when not specified
# - Make sure CompanyBot exists with proper context (prompt) and tool_context