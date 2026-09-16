import re
import logging
import json_repair
from jinja2 import Template
from chatbot.models import PDFTemplates
from chatbot.pdf.shiksha_chaupal.story_images_page import get_report_images_page_html
from datetime import datetime

logger = logging.getLogger('django')


def get_mom_report_html(story, story_vernacular, voice_provider, profile):
    """
    Generate MOM report HTML. Tries to use Jinja2 template from database first,
    falls back to hardcoded HTML if template not found.
    """
    # Extract raw data
    if story.other_params:
        challenges_faced = story.other_params.get('challenges_faced')
        solutions_discussed = story.other_params.get('solutions_discussed')
        remarks = story.other_params.get('remarks')
    else:
        challenges_faced, solutions_discussed, remarks = None, None, None

    translation_json = story_vernacular.translation_json
    if translation_json:
        translation_json = translation_json.get('second_page', {})
    else:
        translation_json = {}

    challenges_char_limit = translation_json.get('challenges_char_limit', None)
    first_challenges_char_limit = translation_json.get('first_challenges_char_limit', None)
    solutions_char_limit = translation_json.get('solutions_char_limit', None)
    remarks_char_limit = translation_json.get('remarks_char_limit', None)

    # Process chunks for Jinja2 template
    challenges_chunks = process_steps_to_chunks(
        raw_data=challenges_faced,
        fallback_text=translation_json.get('no_challenges_faced_text', ""),
        char_limit=challenges_char_limit,
        first_char_limit=first_challenges_char_limit,
        is_challenges=True
    )

    solutions_chunks = process_steps_to_chunks(
        raw_data=solutions_discussed,
        fallback_text=translation_json.get('no_solutions_text', ""),
        char_limit=solutions_char_limit
    )

    remarks_chunks = process_steps_to_chunks(
        raw_data=remarks,
        fallback_text=translation_json.get('no_remarks_text', ""),
        char_limit=remarks_char_limit
    )

    # Get processed user details
    author, address_string, company_logo, date_of_discussion, participants_info, organization = get_user_details(
        story=story, profile=profile, voice_provider=voice_provider, translation_json=translation_json
    )

    if hasattr(story, 'story'):
        story_obj = story.story
    else:
        story_obj = story

    # Get images HTML
    images_html = get_report_images_page_html(story=story_obj)

    # Try to use Jinja2 template from database
    try:
        pdf_template = PDFTemplates.objects.get(template_name='chaupal_mom_report')
        logger.info("[MOM PDF] Using Jinja2 template from database")
        
        # Build context for Jinja2 template with objects
        context = {
            # Core objects for direct access
            'story': story,
            'profile': profile,
            'translation_json': translation_json,
            
            # Processed chunks
            'challenges_chunks': challenges_chunks,
            'solutions_chunks': solutions_chunks,
            'remarks_chunks': remarks_chunks,
            
            # Processed values
            'date_of_discussion': date_of_discussion,
            'participants_info': participants_info,
            'company_logo': company_logo,
            'images_html': images_html,
        }
        
        # Merge constants from template if available
        if pdf_template.constants_json:
            context = {**pdf_template.constants_json, **context}
        
        template = Template(pdf_template.template)
        return template.render(**context)
        
    except PDFTemplates.DoesNotExist:
        logger.warning("[MOM PDF] Template not found, using legacy HTML generation")
        # Fallback to legacy hardcoded HTML
        pass
    except Exception as e:
        logger.error(f"[MOM PDF] Error rendering template: {e}", exc_info=True)
        # Fallback to legacy hardcoded HTML
        pass

    # Legacy fallback: Generate HTML directly
    challenges_html = process_steps(
        raw_data=challenges_faced,
        fallback_text=translation_json.get('no_challenges_faced_text', ""),
        heading=translation_json.get('heading2', "Challenges"),
        char_limit=challenges_char_limit,
        first_char_limit=first_challenges_char_limit,
        is_challenges=True
    )

    solutions_html = process_steps(
        raw_data=solutions_discussed,
        fallback_text=translation_json.get('no_solutions_text', ""),
        heading=translation_json.get('heading3', "Solutions"),
        char_limit=solutions_char_limit
    )

    remarks_html = process_steps(
        raw_data=remarks,
        fallback_text=translation_json.get('no_remarks_text', ""),
        heading=translation_json.get('heading4', "Remarks"),
        char_limit=remarks_char_limit
    )

    organization_html = f"<p>{organization}</p>" if organization else ""
    date_html = f"<p><span>{translation_json.get('dateHeader', 'Date of discussion')}:</span> {date_of_discussion}</p>" if date_of_discussion else ""
    participants_html = f"<p>{participants_info}</p>" if participants_info else ""

    page_html = f"""
    <div class="story-second-page-container">
        <div style="width: 100%; margin-top: 10px;">
            <div style="display: flex; justify-content: end;">
                <img src="{company_logo}" 
                    style="width: 200px; height: auto; object-fit: contain;"
                    alt="Bottom Logo">
            </div>
        </div>
        <h1>{story.title}</h1>
        <p>{author if author else ""}</p>
        {organization_html}
        <p>{address_string}</p>
        {date_html}
        {participants_html}

        {challenges_html if challenges_faced not in [None, [], [""]] else ""}
        {solutions_html if solutions_discussed not in [None, [], [""]] else ""}
        {remarks_html if remarks not in [None, [], [""], ""] else ""}
        {images_html}
    </div>
    """
    return page_html


def process_steps_to_chunks(raw_data, fallback_text, char_limit, first_char_limit=None, is_challenges=False):
    """
    Process steps and return chunks (arrays) for Jinja2 template.
    Similar to process_steps but returns data instead of HTML.
    """
    if isinstance(raw_data, str):
        try:
            if raw_data.strip().startswith("["):
                raw_data = json_repair.repair_json(raw_data, return_objects=True)
            else:
                raw_data = [raw_data]
        except Exception as e:
            raw_data = [fallback_text]

    steps = (
        [clean_escaped_text(step) for step in raw_data] if isinstance(raw_data, list)
        else [clean_escaped_text(raw_data)] if isinstance(raw_data, str)
        else [fallback_text]
    )

    if steps and isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], str):
        steps_text = steps[0]
        split_steps = re.findall(r'\d+\.\s*[^0-9]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
        if not split_steps:
            split_steps = steps
    elif steps and isinstance(steps, str):
        steps_text = " ".join(steps)
        split_steps = re.findall(r'\d+\.\s*[^.]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
    else:
        split_steps = [step.strip() for step in steps if step.strip()]

    # Chunking logic
    chunks = []
    current_chunk = []
    current_length = 0
    chunk_index = 0

    for step in split_steps:
        current_limit = first_char_limit if is_challenges and chunk_index == 0 else char_limit or 1200
        step_len = len(step)

        if current_length + step_len > current_limit and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [step]
            current_length = step_len
            chunk_index += 1
        else:
            current_chunk.append(step)
            current_length += step_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [[fallback_text]]


def clean_escaped_text(text):
    text = text.replace("\\'", "")  # \'  →  '
    text = text.replace('\\"', '')  # \"  →  "
    text = text.replace("\\\\", "")  # \\  →  \
    print("Text: ", text)
    return text


def process_steps(raw_data, fallback_text, char_limit, first_char_limit=None, heading=None, is_challenges=False):
    if isinstance(raw_data, str):
        try:
            if raw_data.strip().startswith("["):
                raw_data = json_repair.repair_json(raw_data, return_objects=True)
            else:
                raw_data = [raw_data]
        except Exception as e:
            raw_data = [fallback_text]

    steps = (
        [clean_escaped_text(step) for step in raw_data] if isinstance(raw_data, list)
        else [clean_escaped_text(raw_data)] if isinstance(raw_data, str)
        else [fallback_text]
    )

    if steps and isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], str):
        steps_text = steps[0]
        split_steps = re.findall(r'\d+\.\s*[^0-9]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
        if not split_steps:
            split_steps = steps
    elif steps and isinstance(steps, str):
        steps_text = " ".join(steps)
        split_steps = re.findall(r'\d+\.\s*[^.]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
    else:
        split_steps = [step.strip() for step in steps if step.strip()]

    # Determine chunking logic
    chunks = []
    current_chunk = []
    current_length = 0
    chunk_index = 0

    for step in split_steps:
        current_limit = first_char_limit if is_challenges and chunk_index == 0 else char_limit or 1200
        step_len = len(step)

        if current_length + step_len > current_limit and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [step]
            current_length = step_len
            chunk_index += 1
        else:
            current_chunk.append(step)
            current_length += step_len

    if current_chunk:
        chunks.append(current_chunk)

    # Build HTML with page breaks between chunks
    full_html = ""
    current_number = 1  # Counter to maintain numbering across chunks
    for i, chunk in enumerate(chunks):
        # Do not apply page-break to the last chunk
        page_break = "split-div1" if i < len(chunks) - 1 else ""
        # Only add page break if it's not the last chunk
        html = (
                f"<div class='{page_break}'>"
                f"<div class='second-main-sec-div'>"
                f"<div class='story-second-page-section'>"
                "<div class='split-div'>"
                + (f"<h2>{heading}</h2>" if heading else "")
                + "<ol class='secondpage-order-list'>"
                + ''.join(f"<li>{current_number + idx}. {step}</li>" for idx, step in enumerate(chunk))
                + "</ol></div></div></div></div>"
        )
        full_html += html
        # Update the current_number after the chunk
        current_number += len(chunk)

    return full_html or fallback_text


def format_participants_count(participants_count, translation_json):
    """Format participants count showing only non-zero values and include total."""
    if not participants_count or not isinstance(participants_count, dict):
        return None

    def safe_int(value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    participant_parts = []
    print("participants_count: ", participants_count)
    total = safe_int(participants_count.get('total'))

    # Get labels from translation_json (fallbacks if not present)
    women_label = translation_json.get('womenLabel', 'Women')
    men_label = translation_json.get('menLabel', 'Men')
    children_label = translation_json.get('childrenLabel', 'Children')

    # Women
    women_count = safe_int(participants_count.get('women'))
    if women_count > 0:
        participant_parts.append(f"{women_count}{women_label.lower()}")

    # Men
    men_count = safe_int(participants_count.get('men'))
    if men_count > 0:
        participant_parts.append(f"{men_count}{men_label.lower()}")

    # Children
    children_count = safe_int(participants_count.get('children'))
    if children_count > 0:
        participant_parts.append(f"{children_count}{children_label.lower()}")

    if not participant_parts and total <= 0:
        return None
    participants_label=translation_json.get('memberHeader', 'Total Participants')
    return f"{participants_label}: {total}" if not participant_parts else f"{participants_label}: {total} [{', '.join(participant_parts)}]"


def get_user_details(story, profile, voice_provider, translation_json):
    company_logo = translation_json.get('main_logo', '')
    print("logo: ", company_logo)

    author = profile.first_name if profile and profile.first_name else ""
    if not profile or not profile.first_name:
        author = story.other_params.get('user_name', '') if story.other_params else ''
    address_string = story.other_params.get('location', '') if story.other_params else ''

    date_of_discussion = story.other_params.get('discussion_date', None)
    date_of_discussion = format_date_to_ddmmyyyy(date_of_discussion)

    # Get organization
    organization = story.other_params.get('organization', '') if story.other_params else ''

    # Process participants count
    participants_count = story.other_params.get('participants_count', None) if story.other_params else None
    participants_info = format_participants_count(participants_count, translation_json)

    return author, address_string, company_logo, date_of_discussion, participants_info, organization


def format_date_to_ddmmyyyy(date_value):
    if isinstance(date_value, datetime):
        return date_value.strftime("%d/%m/%Y")
    elif isinstance(date_value, str):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_value, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
    return ""
