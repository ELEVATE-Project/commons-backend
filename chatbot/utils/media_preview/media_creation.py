import os
import logging

from chatbot.models import CompanyBot
from chatbot.models.story_vernacular_model import StoryVernacular
from chatbot.utils.S3.s3_service import upload_file_to_s3
from chatbot.utils.gotenberg_utils import generate_pdf_with_gotenberg
from chatbot.models.enums import MediaTypeChoices

logger = logging.getLogger('django')


def create_pdf_from_text(text_content, company_bot_id) -> bytes:
    """
    Create a PDF file from text content using Gotenberg HTML-to-PDF service.
    """
    try:
        # Convert text to formatted HTML
        html_content = text_to_html(text_content, company_bot_id)
        
        # Use Gotenberg to convert HTML to PDF
        pdf_content = generate_pdf_with_gotenberg(html_content)
        
        if not pdf_content:
            raise Exception("Gotenberg failed to generate PDF")
        
        logger.info(f"Successfully created PDF with {len(text_content)} characters")
        
        return pdf_content
        
    except Exception as e:
        logger.error(f"Error creating PDF from text: {e}", exc_info=True)
        raise


def text_to_html(text_content, company_bot_id) -> str:
    """
    Convert Markdown text to styled HTML for PDF generation.
    """
    import markdown
    import re

    max_char_per_page = 1500
    try:
        print(f"company_bot_id: {company_bot_id}")
        logger.info(f"company_bot_id: {company_bot_id}")
        company_bot = CompanyBot.objects.filter(id=company_bot_id).first()
        print(f"company_bot: {company_bot}")
        logger.info(f"company_bot: {company_bot}")
        if company_bot:
            story_vernacular = StoryVernacular.objects.filter(
                company_bot=company_bot, language='en'
            ).first()
            print(f"story_vernacular: {story_vernacular}")
            logger.info(f"story_vernacular: {story_vernacular}")
            if story_vernacular and story_vernacular.translation_json:
                logger.info(f"story_vernacular translation_json: {story_vernacular.translation_json}")
                max_char_per_page = story_vernacular.translation_json.get(
                    'page_split_char_len', max_char_per_page
                )
        logger.info(f"Using max_char_per_page: {max_char_per_page}")
    except Exception as e:
        logger.info(f"Could not get max_char_per_page from StoryVernacular: {e}")

    # Markdown → HTML
    html = markdown.markdown(
        text_content,
        extensions=[
            "tables",
            "fenced_code",
            "sane_lists",
            "toc",
            "def_list"
        ]
    )

    # Regex to find block-level elements (with attributes allowed)
    block_pattern = re.compile(
        r'(<h[1-3][^>]*>.*?</h[1-3]>|'
        r'<p[^>]*>.*?</p>|'
        r'<ul[^>]*>.*?</ul>|'
        r'<ol[^>]*>.*?</ol>|'
        r'<table[^>]*>.*?</table>)',
        flags=re.DOTALL
    )

    pages = []
    current_page = ""
    char_count = 0
    last_index = 0

    def is_heading(block: str) -> bool:
        return block.lstrip().startswith("<h")

    def is_content_block(block: str) -> bool:
        return block.lstrip().startswith(("<p", "<ul", "<ol", "<table"))

    for match in block_pattern.finditer(html):
        start, end = match.span()

        # Preserve any content BEFORE this block
        prefix = html[last_index:start]
        if prefix:
            current_page += prefix
            char_count += len(prefix)

        block = match.group()
        current_page += block
        char_count += len(block)

        # Insert page break ONLY after content blocks
        if char_count >= max_char_per_page and is_content_block(block):
            pages.append(current_page)
            current_page = ""
            char_count = 0

        last_index = end

    # Append remaining tail content
    tail = html[last_index:]
    if tail:
        current_page += tail

    if current_page.strip():
        pages.append(current_page)

    # Wrap pages
    paginated_html = ""
    for page in pages:
        paginated_html += f"""
        <div class="page">
            {page}
        </div>
        """

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Open Sans', Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                margin: 2.2cm;
                color: #111;
            }}

            .page {{
                page-break-after: always;
            }}

            .page:last-child {{
                page-break-after: auto;
            }}

            h1 {{
                font-size: 18pt;
                text-align: center;
                margin: 0 0 1.5em 0;
                text-transform: uppercase;
                letter-spacing: 0.4px;
            }}

            h2 {{
                font-size: 14pt;
                margin-top: 1.8em;
                margin-bottom: 0.8em;
                font-weight: 600;
            }}

            h3 {{
                font-size: 12pt;
                margin-top: 1.4em;
                margin-bottom: 0.5em;
                font-weight: 600;
            }}

            p {{
                margin-bottom: 0.9em;
                text-align: left;
            }}

            ul, ol {{
                margin-left: 1.4em;
                margin-bottom: 1em;
            }}

            li {{
                margin-bottom: 0.3em;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 1.4em 0;
                font-size: 9.5pt;
            }}

            th, td {{
                border: 1px solid #555;
                padding: 6px 8px;
                vertical-align: top;
            }}

            th {{
                background-color: #e9ecef;
                font-weight: bold;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        {paginated_html}
    </body>
    </html>
    """

    return html_template


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename and ensure it has .pdf extension.
    """
    try:
        # Remove any path separators
        filename = os.path.basename(filename)
        
        # Remove extension if present
        name_without_ext = os.path.splitext(filename)[0]
        
        # Replace any invalid characters
        safe_name = "".join(c for c in name_without_ext if c.isalnum() or c in (' ', '-', '_'))
        
        # Remove extra spaces and replace with underscores
        safe_name = '_'.join(safe_name.split())
        
        # Ensure it's not empty
        if not safe_name:
            safe_name = "download"
        
        # Add .pdf extension
        return f"{safe_name}.pdf"
        
    except Exception as e:
        logger.error(f"Error sanitizing filename: {e}")
        return "download.pdf"


def create_and_upload_file(
    *,
    content: str,
    filename: str,
    company_bot_id: int,
    session_id: str
) -> dict:
    """
    Create a PDF file from content and upload it to S3.
    """
    try:
        logger.info(f"Creating file for session {session_id}, company_bot {company_bot_id}")
        logger.info(f"Original filename: {filename}, content length: {len(content)} chars")
        
        # Sanitize filename and ensure .pdf extension
        safe_filename = sanitize_filename(filename)
        logger.info(f"Sanitized filename: {safe_filename}")
        
        # Create PDF from content using Gotenberg
        pdf_content = create_pdf_from_text(content, company_bot_id)
        
        logger.info(f"PDF created successfully, size: {len(pdf_content)} bytes")
        
        # Prepare folder structure: chatbot/<company_bot_id>/
        folder_structure = f"chatbot/{company_bot_id}/"
        
        # Upload to S3
        s3_key = upload_file_to_s3(
            file_name=safe_filename,
            file_content=pdf_content,
            content_type=MediaTypeChoices.PDF,
            project_id=None,
            folder_structure=folder_structure
        )
        
        if not s3_key:
            logger.error("Failed to upload file to S3")
            return {
                'success': False,
                'error': 'Failed to upload file to S3'
            }
        
        # Construct media URL
        base = os.getenv("S3_MEDIA_URL")
        media_url = f"{base}{s3_key}"
        
        logger.info(f"File uploaded successfully: {media_url}")
        
        return {
            'success': True,
            'media_url': media_url,
            'file_name': safe_filename,
            's3_key': s3_key
        }
        
    except Exception as e:
        logger.error(f"Error creating and uploading file: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }
