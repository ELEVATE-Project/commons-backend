import os
from django.core.files.base import ContentFile

from chatbot.models import ChatSession
from chatbot.models.story_vernacular_model import StoryVernacular
from chatbot.utils.gotenberg_utils import generate_pdf_with_gotenberg


def format_sources_html(sources):
    print("Sources check:", sources)

    if not sources or not isinstance(sources, dict):
        return '<li>No sources available</li>'

    added_urls = set()
    source_items = []

    for key in ['objective_chunk', 'action_chunk']:
        data_list = sources.get(key)

        if not data_list or not isinstance(data_list, list):
            continue

        for data in data_list:
            if not isinstance(data, dict):
                continue

            title = data.get('title')
            url = data.get('url')

            if title and url and url not in added_urls:
                added_urls.add(url)
                source_items.append(
                    f'<li><a href="{url}" target="_blank">{title}</a></li>'
                )

    if not source_items:
        return '<li>No sources available</li>'

    return (
        "<div class='project-section'>"
        "<div class='section-header'>"
        "<span class='star-icon'>★</span>"
        "<span class='section-title'>Sources</span>"
        "</div>"
        "<div class='section-content'>"
        "<ol class='sources-list'>"
        + "\n".join(source_items) +
        "</ol>"
        "</div>"
        "</div>"
    )


def get_project_report_html(
        project_title,
        author_name,
        location,
        problem_statement,
        objective,
        timeline,
        action_steps,
        language,
        session,
        sources=None
):
    """Generate HTML for project report PDF matching the screenshot design"""

    # Format action steps as numbered list
    action_steps_html = ""
    if action_steps and isinstance(action_steps, list):
        for i, step in enumerate(action_steps, 1):
            action_steps_html += f'<li value="{i}">{step}</li>\n'

    objective_html = ""
    if objective and isinstance(objective, list):
        for i, obj in enumerate(objective, 1):
            objective_html += f'<li value="{i}">{obj}</li>\n'
    else:
        objective_html = objective or ""

    chat_session = ChatSession.objects.filter(session=session).first()
    sources_char_limit=1200
    if chat_session:
        print("ChatSession found!")
        story_vernacular = StoryVernacular.objects.filter(
            company_bot=chat_session.company_bot, language=language
        ).first()
        if story_vernacular:
            print("StoryVernacular found!")
            sources_char_limit = story_vernacular.translation_json.get('sources_char_limit', 1200)

    # Format sources as numbered list
    sources_html = format_sources_html(sources)
    print("sources_html: ", sources_html)
    # Get CSS path (using the story PDF CSS as base)
    css_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "ks_report_pdf.css"))

    # Read CSS file
    try:
        with open(css_path, 'r') as css_file:
            inline_css = css_file.read()
    except:
        # Fallback CSS if file not found
        inline_css = get_project_report_css()

    html_content = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset="utf-8" />
            <title>{project_title}</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200..800&family=Open+Sans:ital,wght@0,300..800;1,300..800&display=swap" rel="stylesheet">
            <style>
                {inline_css}
                {get_project_report_css()}
            </style>
        </head>
        <body>
            <div class="project-report-container">
                <div class="project-header">
                    <h1 class="project-title">{project_title}</h1>
                </div>

                <div class="project-section">
                    <div class="section-header">
                        <span class="star-icon">★</span>
                        <span class="section-title">Problem statement</span>
                    </div>
                    <div class="section-content">
                        {problem_statement}
                    </div>
                </div>

                <div class="project-section">
                    <div class="section-header">
                        <span class="star-icon">★</span>
                        <span class="section-title">Objective</span>
                    </div>
                    <div class="section-content">
                        {
                            f"<ol class='action-steps-list'>{objective_html}</ol>"
                            if isinstance(objective, list)
                            else objective_html
                        }
                    </div>
                </div>

                <div class="project-section">
                    <div class="section-header">
                        <span class="star-icon">★</span>
                        <span class="section-title">Timeline</span>
                    </div>
                    <div class="section-content">
                        {timeline}
                    </div>
                </div>

                <div class="project-section">
                    <div class="section-header">
                        <span class="star-icon">★</span>
                        <span class="section-title">Action steps</span>
                    </div>
                    <div class="section-content">
                        <ol class="action-steps-list">
                            {action_steps_html}
                        </ol>
                    </div>
                </div>

                {sources_html}
            </div>
        </body>
    </html>
    """

    return html_content


def get_project_report_css():
    """Return CSS styles for project report PDF"""
    return """
    /* Project Report Specific Styles */
    body {
        font-family: 'Open Sans', 'Manrope', sans-serif;
        margin: 0;
        padding: 40px;
        color: #333;
        background-color: #ffffff;
    }

    .project-report-container {
        max-width: 800px;
        margin: 0 auto;
        background: white;
        padding: 20px;
    }

    .project-header {
        margin-bottom: 40px;
    }

    .project-title {
        font-size: 24px;
        font-weight: 600;
        color: #2c3e50;
        margin: 0 0 10px 0;
        line-height: 1.3;
    }

    .project-author {
        font-size: 14px;
        color: #666;
        line-height: 1.5;
    }

    .project-section {
        margin-bottom: 30px;
        border: 1px solid #e1e4e8;
        border-radius: 8px;
        padding: 20px;
        background-color: #f8f9fa;
        page-break-inside: avoid;
    }

    .section-header {
        display: flex;
        align-items: center;
        margin-bottom: 15px;
        gap: 8px;
    }

    .star-icon {
        color: #47aa8c;
        font-size: 20px;
    }

    .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #47aa8c;
    }

    .section-content {
        font-size: 14px;
        line-height: 1.6;
        color: #333;
        padding-left: 28px;
    }

    .action-steps-list,
    .sources-list {
        margin: 0;
        padding-left: 20px;
        list-style-type: decimal;
    }

    .action-steps-list li,
    .sources-list li {
        margin-bottom: 10px;
        line-height: 1.6;
    }

    /* Print styles */
    @media print {
        body {
            padding: 20px;
        }

        .project-section {
            break-inside: avoid;
        }
    }
    """


def generate_project_pdf(
        project_title,
        author_name,
        location,
        problem_statement,
        objective,
        timeline,
        action_steps,
        language,
        session,
        sources=None,
        pdf_filename=None,
):
    """Generate PDF for project report"""

    # Generate HTML content
    html_content = get_project_report_html(
        project_title=project_title,
        author_name=author_name,
        location=location,
        problem_statement=problem_statement,
        objective=objective,
        timeline=timeline,
        action_steps=action_steps,
        language=language,
        session=session,
        sources=sources
    )

    # Generate PDF using gotenberg
    pdf_generated = generate_pdf_with_gotenberg(html_content)

    # Set default filename if not provided
    if not pdf_filename:
        pdf_filename = f"{project_title}.pdf" if project_title else "Project_Report.pdf"

    # Create ContentFile
    pdf_content = ContentFile(pdf_generated, name=pdf_filename)

    print(f"PDF report generated: {pdf_filename}")

    return pdf_content