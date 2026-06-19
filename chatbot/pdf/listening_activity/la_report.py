from chatbot.models import StoryTranslation


def get_common_report_html(story, profile, story_vernacular=None):
    # Get data from other_params
    other_params = story.other_params or {}
    question_answers = other_params.get('question_answers', [])
    state = other_params.get('state', '')
    block = other_params.get('block', '')
    district = other_params.get('district', '')
    company_logo = other_params.get('company_logo', '')

    # Get title and logo from story_vernacular if available
    title = story.title
    char_limit = 800  # More conservative default character limit per page
    qa_per_page = 3  # Default QA pairs per page
    max_page_height = 'auto'  # Default page height constraint

    if story_vernacular:
        translation_json = story_vernacular.translation_json or {}
        title = translation_json.get('title', story.title)
        company_logo = translation_json.get('main_logo', company_logo)

        # Enhanced pagination settings from translation_json
        qa_box_height = translation_json.get('qa_box_height', 'auto')
        char_limit = translation_json.get('qa_char_limit', char_limit)
        qa_per_page = translation_json.get('qa_per_page', qa_per_page)
        max_page_height = translation_json.get('max_page_height', max_page_height)

        # Additional page control settings
        force_page_break_after = translation_json.get('force_page_break_after', None)  # QA numbers to force break after
        min_qa_per_page = translation_json.get('min_qa_per_page', 1)  # Minimum QAs before allowing page break
        page_break_strategy = translation_json.get('page_break_strategy', 'mixed')  # 'char_limit', 'qa_count', 'mixed'

    else:
        qa_box_height = 'auto'
        force_page_break_after = None
        min_qa_per_page = 1
        page_break_strategy = 'mixed'

    # Build location string
    location_parts = [part for part in [block, district, state] if part]
    location_string = ", ".join(location_parts)

    # Process QA pairs with enhanced pagination control
    qa_chunks = chunk_qa_with_page_control(
        question_answers,
        char_limit,
        qa_box_height,
        qa_per_page,
        max_page_height,
        force_page_break_after,
        min_qa_per_page,
        page_break_strategy,
        location_string,
        company_logo
    )

    # Build HTML with proper page structure and different layouts for first vs subsequent pages
    full_html = ""
    for i, chunk_html in enumerate(qa_chunks):
        if i == 0:
            # First page layout - logo, location and title
            full_html += f"""
            <div class="qa-report-container first-page">
                <div class="qa-first-page-header">
                    {f'<img src="{company_logo}" class="qa-first-page-logo" alt="Company Logo">' if company_logo else ''}
                    <div class="qa-first-page-location">{location_string}</div>
                    <div class="qa-first-page-title">{title}</div>
                </div>
                <div class="qa-content first-page-content">
                    {chunk_html}
                </div>
            </div>
            """
        else:
            # Subsequent pages - only logo in top right, minimal header
            full_html += f"""
            <div class="qa-page-break"></div>
            <div class="qa-report-container continuation-page">
                <div class="qa-continuation-header">
                    {f'<img src="{company_logo}" class="qa-continuation-logo" alt="Company Logo">' if company_logo else ''}
                </div>
                <div class="qa-continuation-spacer"></div>
                <div class="qa-content qa-content-continued">
                    {chunk_html}
                </div>
            </div>
            """

    return full_html


def chunk_qa_with_page_control(question_answers, char_limit, qa_box_height, qa_per_page,
                               max_page_height, force_page_break_after, min_qa_per_page,
                               page_break_strategy, location_string, company_logo):
    """
    Enhanced QA chunking with multiple pagination strategies and controls
    """
    chunks = []
    current_chunk_html = ""
    current_char_count = 0
    current_qa_count = 0
    display_number = 1  # Separate counter for displayed question numbers

    for i, qa in enumerate(question_answers, 1):
        # Check if QA has both question and non-empty answer
        if (isinstance(qa, dict) and
                qa.get('question') and
                qa.get('answer') and
                str(qa.get('answer')).strip()):  # Check for non-empty answer

            qa_html = f"""
            <div class="qa-section" style="min-height: {qa_box_height};" data-qa-number="{display_number}">
                <div class="qa-question-wrapper">
                    <span class="question-number">{display_number}.</span>
                    <span class="question-text">{clean_escaped_text(qa['question'])}</span>
                </div>
                <div class="qa-answer-wrapper">
                    <span class="answer-arrow">→</span>
                    <span class="answer-text">{clean_escaped_text(qa['answer'])}</span>
                </div>
            </div>
            """

            qa_text_length = len(qa.get('question', '')) + len(qa.get('answer', ''))

            # Determine if we should break to a new page
            should_break = False

            if page_break_strategy == 'char_limit':
                # Character limit strategy
                should_break = (current_char_count + qa_text_length > char_limit and
                                current_qa_count >= min_qa_per_page)

            elif page_break_strategy == 'qa_count':
                # QA count strategy
                should_break = (current_qa_count >= qa_per_page and
                                current_qa_count >= min_qa_per_page)

            elif page_break_strategy == 'mixed':
                # Mixed strategy (default) - break on either condition
                should_break = ((current_char_count + qa_text_length > char_limit or
                                 current_qa_count >= qa_per_page) and
                                current_qa_count >= min_qa_per_page)

            # Force page break after specific QA numbers (use display_number for comparison)
            if force_page_break_after and display_number - 1 in force_page_break_after:
                should_break = True

            # Execute page break if conditions are met and we have content
            if should_break and current_chunk_html:
                chunks.append(current_chunk_html)
                current_chunk_html = qa_html
                current_char_count = qa_text_length
                current_qa_count = 1
            else:
                current_chunk_html += qa_html
                current_char_count += qa_text_length
                current_qa_count += 1

            # Increment display number only when we actually display a QA
            display_number += 1

    # Add the last chunk if there's any content
    if current_chunk_html:
        chunks.append(current_chunk_html)

    return chunks


def estimate_content_height(qa_count, qa_box_height, base_height=200):
    """
    Estimate the total height of content based on QA count and box height
    Useful for max_page_height calculations
    """
    if qa_box_height == 'auto':
        estimated_qa_height = 150  # Default estimated height per QA
    else:
        try:
            estimated_qa_height = int(qa_box_height.replace('px', ''))
        except:
            estimated_qa_height = 150

    return base_height + (qa_count * estimated_qa_height)


def get_optimal_pagination_settings(question_answers, target_pages=None):
    """
    Calculate optimal pagination settings based on content analysis
    Only counts Q&As that have non-empty answers
    """
    # Filter out Q&As with empty answers for calculation
    valid_qas = [qa for qa in question_answers
                 if isinstance(qa, dict) and qa.get('question') and
                 qa.get('answer') and str(qa.get('answer')).strip()]

    total_qas = len(valid_qas)
    total_chars = sum(len(qa.get('question', '')) + len(qa.get('answer', ''))
                      for qa in valid_qas)

    if target_pages and total_qas > 0:
        # Calculate settings to fit content into target number of pages
        qa_per_page = max(1, total_qas // target_pages)
        char_limit = max(400, total_chars // target_pages)
    else:
        # Use default heuristics
        avg_chars_per_qa = total_chars / total_qas if total_qas > 0 else 400

        if avg_chars_per_qa > 200:
            qa_per_page = 3
            char_limit = 600
        else:
            qa_per_page = 4
            char_limit = 800

    return {
        'qa_per_page': qa_per_page,
        'qa_char_limit': char_limit,
        'estimated_pages': (total_qas + qa_per_page - 1) // qa_per_page if total_qas > 0 else 0
    }


def clean_escaped_text(text):
    if not text:
        return ""
    text = str(text).replace("\\'", "'")  # \'  →  '
    text = text.replace('\\"', '"')  # \"  →  "
    text = text.replace("\\\\", "\\")  # \\  →  \
    return text.strip()


def get_generic_story_in_language(story, language='en'):
    """Get generic story content in specified language"""
    if language == 'en' or language == story.language:
        return {
            'title': story.title,
            'content': story.content,
            'tweet': story.tweet,
            'objective': story.objective,
            'action_steps': story.action_steps,
            'impact': story.impact,
            'micro_improvement': story.micro_improvement,
            'blurb': story.blurb,
            'other_params': story.other_params,
        }

    try:
        translation = story.translations.get(language=language)
        return {
            'title': translation.title,
            'content': translation.content,
            'tweet': translation.tweet,
            'objective': translation.objective,
            'action_steps': translation.action_steps,
            'impact': translation.impact,
            'micro_improvement': translation.micro_improvement,
            'blurb': translation.blurb,
            'other_params': translation.other_params,
        }
    except StoryTranslation.DoesNotExist:
        return get_generic_story_in_language(story, 'en')
