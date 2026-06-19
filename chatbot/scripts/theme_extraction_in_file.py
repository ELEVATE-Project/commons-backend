import json
import os
import logging
from datetime import datetime
import json_repair
from chatbot.llm_models.llm_script import handle_bedrock_model


logger = logging.getLogger('django')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


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


def get_story_count(language=None, session_type=None, start_date=None, end_date=None):
    """Get count of stories matching the given filters"""
    # Build query
    query = Story.objects.all()

    # Apply filters
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        query = query.filter(session__in=session_ids)

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    if language:
        query = query.filter(language=language)

    total_count = query.count()

    # Count stories with themes
    stories_with_themes = query.filter(
        other_params__themes__isnull=False
    ).count()

    # Count by language if no language filter
    language_counts = {}
    if not language:
        language_counts = dict(query.values_list('language').annotate(count=models.Count('id')))

    print(f"\n{'=' * 60}")
    print("STORY COUNT SUMMARY")
    if language:
        print(f"Language filter: {language}")
    if session_type:
        print(f"Session type filter: {session_type}")
    if start_date or end_date:
        print(f"Date range: {start_date or 'beginning'} to {end_date or 'now'}")
    print(f"{'=' * 60}")
    print(f"Total stories: {total_count}")
    print(
        f"Stories with themes: {stories_with_themes} ({stories_with_themes / total_count * 100:.1f}%)" if total_count > 0 else "Stories with themes: 0")
    print(f"Stories without themes: {total_count - stories_with_themes}")

    if language_counts:
        print(f"\nBreakdown by language:")
        for lang, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {lang}: {count}")

    print(f"{'=' * 60}\n")

    return {
        'total': total_count,
        'with_themes': stories_with_themes,
        'without_themes': total_count - stories_with_themes,
        'language_breakdown': language_counts
    }


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
        'skipped': 0
    }

    for idx, story in enumerate(stories, 1):
        print(f"[{idx}/{stories.count()}] Processing Story ID: {story.id}")

        result = extract_themes_for_story(story)
        print(f"    {result}")

        if "✅" in result:
            results['success'] += 1
        elif "❌" in result:
            results['failed'] += 1
        else:
            results['skipped'] += 1

    print(f"\n{'=' * 60}")
    summary = f"Theme extraction completed:\n"
    summary += f"  - Successfully extracted: {results['success']}\n"
    summary += f"  - Failed: {results['failed']}\n"
    summary += f"  - Skipped: {results['skipped']}\n"
    summary += f"  - Total processed: {stories.count()}"
    print(summary)
    print(f"{'=' * 60}\n")
    logger.info(summary)
    return results


from chatbot.models import Story, ChatSession, CompanyChat, CompanyBot
from chatbot.utils.chat_utils import format_message_as_per_bedrock_format
from jinja2 import Template
from django.db import models

# Master themes file path
MASTER_THEMES_FILE = 'master_themes.json'


def get_master_themes():
    """Get master themes from file"""
    try:
        if os.path.exists(MASTER_THEMES_FILE):
            with open(MASTER_THEMES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'domain_themes': data.get('domain_themes', []),
                    'issue_themes': data.get('issue_themes', [])
                }
        else:
            # Create empty file if not exists
            empty_themes = {
                'domain_themes': [],
                'issue_themes': [],
                'last_updated': datetime.now().isoformat()
            }
            save_master_themes([], [])
            return {
                'domain_themes': [],
                'issue_themes': []
            }
    except Exception as e:
        logger.error(f"Error loading master themes: {str(e)}")
        return {'domain_themes': [], 'issue_themes': []}


def save_master_themes(domain_themes, issue_themes):
    """Save master themes to file"""
    try:
        data = {
            'domain_themes': sorted(list(set(domain_themes))),
            'issue_themes': sorted(list(set(issue_themes))),
            'last_updated': datetime.now().isoformat(),
            'total_domain_themes': len(set(domain_themes)),
            'total_issue_themes': len(set(issue_themes))
        }

        with open(MASTER_THEMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(domain_themes)} domain themes and {len(issue_themes)} issue themes")
        return True
    except Exception as e:
        logger.error(f"Error saving master themes: {str(e)}")
        return False


def update_master_themes(new_domain_themes, new_issue_themes):
    """Update master themes with new ones"""
    try:
        current_themes = get_master_themes()

        # Merge and deduplicate
        updated_domain = set(current_themes['domain_themes']) | set(new_domain_themes)
        updated_issues = set(current_themes['issue_themes']) | set(new_issue_themes)

        # Find what's new
        new_domains = set(new_domain_themes) - set(current_themes['domain_themes'])
        new_issues = set(new_issue_themes) - set(current_themes['issue_themes'])

        if new_domains or new_issues:
            save_master_themes(list(updated_domain), list(updated_issues))
            logger.info(f"Added {len(new_domains)} new domain themes and {len(new_issues)} new issue themes")
            return {'new_domains': list(new_domains), 'new_issues': list(new_issues)}

        return {'new_domains': [], 'new_issues': []}
    except Exception as e:
        logger.error(f"Error updating master themes: {str(e)}")
        return {'new_domains': [], 'new_issues': []}


def extract_themes_for_story(story):
    """Extract themes from a single story"""
    try:
        # Check if already has themes
        if story.other_params and 'themes' in story.other_params:
            existing = story.other_params['themes']
            logger.info(f"Story {story.id} has existing themes, re-extracting...")

        # Get session and bot
        session = ChatSession.objects.get(session=story.session)
        if not session.company_bot:
            return f"❌ No company_bot found for session {story.session}"

        # Get theme extraction bot
        theme_bot = CompanyBot.objects.filter(route='/chaupal-theme-script').first()
        if not theme_bot:
            return f"❌ Theme extraction bot not found"

        # Get master themes
        master_themes = get_master_themes()

        # Generate prompt from bot context
        if not theme_bot.context:
            return f"❌ Theme bot has no context/prompt configured"

        template = Template(theme_bot.context)
        prompt = template.render(
            domain_themes=master_themes['domain_themes'],
            issue_themes=master_themes['issue_themes']
        )

        # Get chat history
        company_chats = CompanyChat.objects.filter(session=story.session).order_by('created_at')
        messages = format_message_as_per_bedrock_format(chats=company_chats)

        # Get tools from bot
        if not theme_bot.tool_context:
            return f"❌ Theme bot has no tool_context configured"

        try:
            tools = json.loads(theme_bot.tool_context)
        except Exception as e:
            return f"❌ Invalid tool_context in theme bot: {str(e)}"

        # Call LLM
        response = handle_bedrock_model(
            system_prompt=[{"text": prompt}],
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

        if result and isinstance(result, dict):
            domain_themes = result.get('domain_themes', [])
            issue_themes = result.get('issue_themes', [])

            if domain_themes or issue_themes:
                # Update master themes if new ones found
                new_themes = update_master_themes(domain_themes, issue_themes)

                if new_themes['new_domains'] or new_themes['new_issues']:
                    logger.info(
                        f"Story ID {story.id} introduced new themes - Domains: {new_themes['new_domains']}, Issues: {new_themes['new_issues']}")

                # Save to story
                if not story.other_params:
                    story.other_params = {}

                story.other_params['themes'] = {
                    'domain_themes': domain_themes,
                    'issue_themes': issue_themes
                }
                story.save(update_fields=['other_params'])

                return f"✅ Extracted - Domain: {domain_themes}, Issues: {issue_themes}"
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
        logger.error(f"Error extracting themes for story {story.id}: {str(e)}")
        return f"❌ Error: {str(e)}"


def extract_themes_for_all_stories(start=0, end=None, language=None, session_type=None, start_date=None, end_date=None):
    """Extract themes for stories with optional filters"""
    # Build query
    stories_query = Story.objects.all()

    # Apply session type filter if provided
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        stories_query = stories_query.filter(session__in=session_ids)
        logger.info(f"Filtering stories by session type: {session_type}")

    # Apply date range filter if provided
    if start_date or end_date:
        if start_date:
            stories_query = stories_query.filter(created_at__gte=start_date)
        if end_date:
            stories_query = stories_query.filter(created_at__lte=end_date)
        logger.info(f"Filtering stories by date range: {start_date} to {end_date}")

    # Apply language filter if provided
    if language:
        stories_query = stories_query.filter(language=language)
        logger.info(f"Filtering stories by language: {language}")

    stories_query = stories_query.order_by('-id')

    # Apply range
    if end:
        stories = stories_query[start:end]
    else:
        stories = stories_query[start:]

    total_count = stories.count()

    print(f"\n{'=' * 60}")
    print(f"Processing {total_count} stories (start: {start}, end: {end or 'all'})")
    if language:
        print(f"Language filter: {language}")
    if session_type:
        print(f"Session type filter: {session_type}")
    if start_date or end_date:
        print(f"Date range: {start_date or 'beginning'} to {end_date or 'now'}")
    print(f"{'=' * 60}\n")

    results = {
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    for idx, story in enumerate(stories, 1):
        print(f"[{idx}/{total_count}] Story ID: {story.id} (Language: {story.language})")

        result = extract_themes_for_story(story)
        print(f"    {result}")

        if "✅" in result:
            results['success'] += 1
        elif "❌" in result:
            results['failed'] += 1
        else:
            results['skipped'] += 1

        # Progress update every 10
        if idx % 10 == 0:
            print(f"\n--- Progress: {idx}/{total_count} ---")
            print(f"Success: {results['success']}, Failed: {results['failed']}, Skipped: {results['skipped']}\n")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY:")
    print(f"  - Success: {results['success']}")
    print(f"  - Failed: {results['failed']}")
    print(f"  - Skipped: {results['skipped']}")
    print(f"  - Total: {total_count}")
    print(f"{'=' * 60}\n")

    return results


def extract_themes_batch(batch_size=100, language=None, session_type=None, start_date=None, end_date=None):
    """Process stories in batches with multiple filters"""
    # Get total count
    query = Story.objects.all()

    # Apply filters for count
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        query = query.filter(session__in=session_ids)

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    if language:
        query = query.filter(language=language)

    total_stories = query.count()

    print(f"\n{'=' * 60}")
    print(f"Total stories: {total_stories}")
    print(f"Batch size: {batch_size}")
    if language:
        print(f"Language filter: {language}")
    if session_type:
        print(f"Session type filter: {session_type}")
    if start_date or end_date:
        print(f"Date range: {start_date or 'beginning'} to {end_date or 'now'}")
    print(f"{'=' * 60}\n")

    processed = 0
    overall_results = {
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    batch_num = 1
    while processed < total_stories:
        print(f"\n🔄 Batch {batch_num}: stories {processed} to {min(processed + batch_size, total_stories)}")

        batch_results = extract_themes_for_all_stories(
            start=processed,
            end=processed + batch_size,
            language=language,
            session_type=session_type,
            start_date=start_date,
            end_date=end_date
        )

        # Aggregate results
        for key in overall_results:
            overall_results[key] += batch_results.get(key, 0)

        processed += batch_size
        batch_num += 1

        # Small delay between batches
        import time
        time.sleep(2)

    print(f"\n{'=' * 60}")
    print("FINAL SUMMARY:")
    print(f"  - Total processed: {total_stories}")
    print(f"  - Success: {overall_results['success']}")
    print(f"  - Failed: {overall_results['failed']}")
    print(f"  - Skipped: {overall_results['skipped']}")
    print(f"{'=' * 60}\n")

    return overall_results


def view_story_themes(story_id):
    """View themes for a specific story"""
    try:
        story = Story.objects.get(id=story_id)
        themes = story.other_params.get('themes', {}) if story.other_params else {}

        print(f"\nStory ID: {story_id}")
        print(f"Title: {story.title}")
        print(f"Language: {story.language}")
        print(f"Domain Themes: {themes.get('domain_themes', [])}")
        print(f"Issue Themes: {themes.get('issue_themes', [])}")

        return themes
    except Story.DoesNotExist:
        print(f"Story {story_id} not found")
        return None


def view_master_themes():
    """View current master themes"""
    themes = get_master_themes()

    print(f"\n{'=' * 60}")
    print("MASTER THEMES")
    print(f"{'=' * 60}")

    print(f"\nDomain Themes ({len(themes['domain_themes'])}):")
    print("-" * 40)
    for i, theme in enumerate(sorted(themes['domain_themes']), 1):
        print(f"{i:3}. {theme}")

    print(f"\nIssue Themes ({len(themes['issue_themes'])}):")
    print("-" * 40)
    for i, theme in enumerate(sorted(themes['issue_themes']), 1):
        print(f"{i:3}. {theme}")

    print(f"{'=' * 60}\n")

    return themes


def get_theme_statistics(language=None, session_type=None, start_date=None, end_date=None):
    """Get statistics about theme usage with multiple filters"""
    domain_count = {}
    issue_count = {}
    total_stories = 0

    # Build query
    query = Story.objects.filter(
        other_params__themes__isnull=False
    )

    # Apply filters
    if session_type:
        session_ids = list(
            ChatSession.objects.filter(session_type=session_type)
            .values_list('session', flat=True)
        )
        query = query.filter(session__in=session_ids)

    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    if language:
        query = query.filter(language=language)

    # Count occurrences
    for story in query:
        if story.other_params and 'themes' in story.other_params:
            themes = story.other_params['themes']
            total_stories += 1

            for theme in themes.get('domain_themes', []):
                domain_count[theme] = domain_count.get(theme, 0) + 1

            for theme in themes.get('issue_themes', []):
                issue_count[theme] = issue_count.get(theme, 0) + 1

    # Sort by frequency
    sorted_domains = sorted(domain_count.items(), key=lambda x: x[1], reverse=True)
    sorted_issues = sorted(issue_count.items(), key=lambda x: x[1], reverse=True)

    print(f"\n{'=' * 60}")
    print("THEME STATISTICS")
    if language:
        print(f"Language: {language}")
    if session_type:
        print(f"Session type: {session_type}")
    if start_date or end_date:
        print(f"Date range: {start_date or 'beginning'} to {end_date or 'now'}")
    print(f"{'=' * 60}")
    print(f"Total stories with themes: {total_stories}")

    print(f"\nTop Domain Themes:")
    print(f"{'Theme':<40} {'Count':<10} {'%':<10}")
    print("-" * 60)
    for theme, count in sorted_domains[:10]:
        pct = (count / total_stories * 100) if total_stories > 0 else 0
        print(f"{theme:<40} {count:<10} {pct:.1f}%")

    print(f"\nTop Issue Themes:")
    print(f"{'Theme':<40} {'Count':<10} {'%':<10}")
    print("-" * 60)
    for theme, count in sorted_issues[:10]:
        pct = (count / total_stories * 100) if total_stories > 0 else 0
        print(f"{theme:<40} {count:<10} {pct:.1f}%")

    print(f"{'=' * 60}\n")

    return {
        'domain_themes': sorted_domains,
        'issue_themes': sorted_issues,
        'total_stories': total_stories
    }

# ============================================================================
# USAGE EXAMPLES
# ============================================================================
#
# 1. Extract themes for all stories:
#    extract_themes_for_all_stories()
#
# 2. Extract themes with language filter:
#    extract_themes_for_all_stories(language='hi')
#
# 3. Extract themes with session type filter:
#    from chatbot.models import ChatType
#    extract_themes_for_all_stories(session_type=ChatType.shikshaChaupal)
#
# 4. Extract themes with date range:
#    from datetime import datetime
#    from django.utils.timezone import make_aware
#    start = make_aware(datetime(2025, 1, 1))
#    end = make_aware(datetime(2025, 1, 31))
#    extract_themes_for_all_stories(start_date=start, end_date=end)
#
# 5. Combine multiple filters:
#    extract_themes_for_all_stories(
#        language='hi',
#        session_type=ChatType.shikshaChaupal,
#        start_date=start,
#        end_date=end
#    )
#
# 6. Batch processing with filters:
#    extract_themes_batch(
#        batch_size=100,
#        language='en',
#        session_type=ChatType.normal
#    )
#
# 7. Extract themes for specific story IDs:
#    story_ids = [123, 456, 789]
#    extract_themes_for_specific_stories(story_ids)
#
# 8. Get story count with filters:
#    get_story_count()  # All stories
#    get_story_count(language='hi', session_type=ChatType.shikshaChaupal)
#
# 9. View story themes:
#    view_story_themes(12345)
#
# 10. View master themes:
#     view_master_themes()
#
# 11. Get theme statistics with filters:
#     get_theme_statistics()  # All
#     get_theme_statistics(language='hi', session_type=ChatType.shikshaChaupal)
#
# 12. Manually update master themes:
#     update_master_themes(
#         new_domain_themes=['technology', 'environment'],
#         new_issue_themes=['digital divide', 'climate change']
#     )
#