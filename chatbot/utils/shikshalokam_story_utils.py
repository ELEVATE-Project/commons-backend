from chatbot.models import StoryMedia, MediaTypeChoices, CompanyChat, Profile, Story, ChatSession, SessionFlowName, \
    CompanyBot, Flow, Voice, StoryLanguageChoices
from chatbot.models.company_models import PDFTemplates
from chatbot.models.enums import UserTypeChoices, VoiceType
from chatbot.models.story_models import StoryTranslation
from chatbot.models.story_vernacular_model import StoryVernacular
from chatbot.pdf.listening_activity.la_report import get_common_report_html
from chatbot.pdf.shiksha_chaupal.mom_report import get_mom_report_html
from chatbot.pdf.story_first_page import get_first_page_html
from chatbot.pdf.story_images_page import get_story_images_page_html
from chatbot.pdf.story_secondpage import get_story_secondpage_html
from chatbot.pdf.story_thirdpage import get_thirdpage_html
from chatbot.serializer.story_serializer import StoryCreateSerializer
from chatbot.utils.elevate.project_detail import fetch_existing_project_attachments
from chatbot.utils.gotenberg_utils import generate_pdf_with_gotenberg
from chatbot.utils.media_utils import upload_to_cloud
from chatbot.utils.shikshalokam_mitra_utils import get_stored_conversation, get_stored_chathistory
from django.core.files.base import ContentFile
from jinja2 import Template
from shikshalokam.models import Project, Task
from shikshalokam.models.project_vernacular_model import ProjectVernacular
from shikshalokam.serializer import ProjectSerializer
import json
import os
import re
import requests
import traceback
import logging

logger = logging.getLogger("django")

base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def save_shikshalokam_story(
        story, problem_statement, chat_history, access_token, project_id, session,
        profile, conversation, flow
):
    try:
        html_content = get_story_html(story=story, profile=profile, flow=flow)

        pdf_generated = generate_pdf_with_gotenberg(html_content)
        pdf_file_name = story.title
        if not pdf_file_name or pdf_file_name == '':
            pdf_file_name = 'Improvement_story'
        pdf_file_name = f"{pdf_file_name}.pdf"
        pdf_content = ContentFile(pdf_generated, name=pdf_file_name)
        print("pdf_content: ", pdf_content)
        print("pdf_content type: ", type(pdf_content))
        # StoryMedia.objects.create(
        #     name=pdf_file_name,
        #     file=pdf_content,
        #     story=story,
        #     include_in_story=False,
        #     media_type=MediaTypeChoices.PDF
        # )

        story_media, created = StoryMedia.objects.update_or_create(
            story=story,
            media_type=MediaTypeChoices.PDF,
            defaults={
                "name": pdf_file_name,
                "file": pdf_content,
                "include_in_story": False
            }
        )

        if created:
            print("New PDF created")
        else:
            print("Existing PDF updated")

        if access_token in [None, "", "null"] or not session or not project_id or flow != SessionFlowName.Reflection:
            print("Not calling shikshalokam api as access_tokne or session or project_id is missing")
            return
        upload_response_json = upload_to_cloud(session_value=session, access_token=access_token, story=story)
        attachments = upload_response_json.get('attachments')
        print("attachments: ", attachments)

        pdf_information = upload_response_json.get('pdfInformation')
        print("pdf_information: ", pdf_information)


        request_body = {
            "story": {
                "title": story.title,
                "problemStatement": problem_statement,
                "objective": story.objective,
                "timeline": "",
                "actionSteps": story.action_steps or [],
                "resources": [],
                "impact": story.impact,
                "summary": story.content,
                "authorName": story.author.first_name if story.author else "",
                "location": story.location or "",
                "conversation": conversation,
                "chatHistory": chat_history,
                "attachments": attachments,
                "pdfInformation": pdf_information,
            }
        }
        print("request_body: ", request_body)
        print("type: ", type(request_body))
        print("type: ", type(request_body.get("story")))

        url = f"https://{base_url}/userProjects/addStory/{project_id}"
        print("Using url: ", url)

        headers = {
            "X-auth-token": access_token,
        }

        response = requests.put(url, headers=headers, json=request_body)
        print("Res:", response)
        print("response: ", response.json())
        response.raise_for_status()

        print(f"Story successfully saved to Shikshalokam: {response.status_code}")
    except Exception as e:
        traceback.print_exc()
        print(f"Failed to save story to Shikshalokam: {str(e)}")


def save_project_story( story, problem_statement, chat_history, access_token, project_id, session, profile, conversation, flow):
    try:
        session_data = ChatSession.objects.get(session=session)
        html_content = get_html_from_template(story=story, profile=profile, flow=flow, auth=access_token is not None, language=session_data.language)

        pdf_generated = generate_pdf_with_gotenberg(html_content)
        pdf_file_name = story.title
        if not pdf_file_name or pdf_file_name == '':
            pdf_file_name = 'Improvement_story'
        pdf_file_name = f"{pdf_file_name}.pdf"
        pdf_content = ContentFile(pdf_generated, name=pdf_file_name)
        print("pdf_content: ", pdf_content)
        print("pdf_content type: ", type(pdf_content))

        story_media, created = StoryMedia.objects.update_or_create(
            story=story,
            media_type=MediaTypeChoices.PDF,
            defaults={
                "name": pdf_file_name,
                "file": pdf_content,
                "include_in_story": False
            }
        )

        if created:
            print("New PDF created")
        else:
            print("Existing PDF updated")

        if access_token in [None, "", "null"] or not session or not project_id or flow != SessionFlowName.Reflection:
            print("Not calling shikshalokam api as access_tokne or session or project_id is missing")
            return
        upload_response_json = upload_to_cloud(session_value=session, access_token=access_token, story=story)
        attachments = upload_response_json.get('attachments')
        print("attachments: ", attachments)

        pdf_information = upload_response_json.get('pdfInformation')
        print("pdf_information: ", pdf_information)


        request_body = {
            "story": {
                "title": story.title,
                "problemStatement": problem_statement,
                "objective": story.objective,
                "timeline": "",
                "actionSteps": story.action_steps or [],
                "resources": [],
                "impact": story.impact,
                "summary": story.content,
                "authorName": story.author.first_name if story.author else "",
                "location": story.location or "",
                "conversation": conversation,
                "chatHistory": chat_history,
                "attachments": attachments,
                "pdfInformation": pdf_information,
            }
        }
        print("request_body: ", request_body)
        print("type: ", type(request_body))
        print("type: ", type(request_body.get("story")))

        url = f"https://{base_url}/userProjects/addStory/{project_id}"
        print("Using url: ", url)

        headers = {
            "X-auth-token": access_token,
        }

        response = requests.put(url, headers=headers, json=request_body)
        print("Res:", response)
        print("response: ", response.json())
        response.raise_for_status()

        print(f"Story successfully saved to Shikshalokam: {response.status_code}")
    except Exception as e:
        traceback.print_exc()
        print(f"Failed to save story to Shikshalokam: {str(e)}")
        raise e


def get_story_html(story, profile, flow):
    project = Project.objects.filter(story=story).first()
    if flow in [SessionFlowName.LoginMiStory, SessionFlowName.SsoFlow, SessionFlowName.GuestMiStory,
                SessionFlowName.Reflection, SessionFlowName.YLC]:
        css_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../pdf/story_pdf.css"))
    elif flow in [SessionFlowName.GuestDiscussion, SessionFlowName.LoginDiscussion]:
        css_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../pdf/shiksha_chaupal/mom_report_pdf.css"))
    else:
        css_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../pdf/listening_activity/la_report_pdf.css"))
    if profile:
        if flow in [SessionFlowName.LoginMiStory, SessionFlowName.SsoFlow, SessionFlowName.Reflection]:
            company_bot = CompanyBot.objects.get(route='/story')
        elif flow in [SessionFlowName.GuestMiStory]:
            company_bot = CompanyBot.objects.get(route='/guest-story')
        elif flow in [SessionFlowName.GuestDiscussion, SessionFlowName.LoginDiscussion]:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/chaupal-story')
        else:
            company_bot = CompanyBot.objects.get(company=profile.company, route=f'/{flow}-story')
    else:
        if flow in [SessionFlowName.LoginMiStory, SessionFlowName.SsoFlow, SessionFlowName.Reflection]:
            company_bot = CompanyBot.objects.get(route='/story')
        elif flow in [SessionFlowName.GuestMiStory]:
            company_bot = CompanyBot.objects.get(route='/guest-story')
        elif flow in [SessionFlowName.GuestDiscussion, SessionFlowName.LoginDiscussion]:
            company_bot = CompanyBot.objects.get(route='/chaupal-story')
        else:
            company_bot = CompanyBot.objects.get(company=profile.company, route=f'/{flow}-story')

    translation_languages = list(story.translations.values_list('language', flat=True))
    chat_session = ChatSession.objects.filter(session=story.session).first()

    language_used = (
        chat_session.language or
        translation_languages[0] if translation_languages else
        (project.project_language if project else None) or
        story.language or
        'en'
    )

    voice_provider = Voice.objects.filter(
        company_bot=company_bot, type=VoiceType.TextToText, language=language_used
    ).first()

    story_vernacular = StoryVernacular.objects.filter(
        company_bot=company_bot, language=language_used
    ).first()
    if story_vernacular:
        logger.info(f"story_vernacular found: {story_vernacular.id} & {story_vernacular.company_bot} & {story_vernacular.language}")
    if language_used == 'en':
        object_to_pass = story
        if project:
            project_serializer = ProjectSerializer(project)
            project_to_pass = project_serializer.data
        else:
            project_to_pass = None
    else:
        try:
            story_translation = story.translations.get(language=language_used)
            object_to_pass = story_translation
        except StoryTranslation.DoesNotExist:
            logger.info(f"Translation for language '{language_used}' not found, using English story")
            object_to_pass = story
        if project:
            try:
                project_vernacular = project.project_vernacular.get(language=language_used)
                project_details = json.loads(project_vernacular.details)
                project_to_pass = project_details.get('project', {})
            except ProjectVernacular.DoesNotExist:
                print(f"Project vernacular for language '{language_used}' not found, using English project")
                project_serializer = ProjectSerializer(project)
                project_to_pass = project_serializer.data
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing project vernacular details: {e}, using English project")
                project_serializer = ProjectSerializer(project)
                project_to_pass = project_serializer.data
        else:
            print("No project found for story, using None for project_to_pass")
            project_to_pass = None

    if project_to_pass:
        pdf_file_name = project_to_pass.get('expected_title') or project_to_pass.get('actual_title') or "Improvement_story"
    else:
        pdf_file_name = object_to_pass.title or "Improvement_story"

    print("Using pdf name: ", pdf_file_name)
    with open(css_path, 'r') as css_file:
        inline_css = css_file.read()
    html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="utf-8" />
                    <title>{pdf_file_name}</title>
                    <link rel="preconnect" href="https://fonts.googleapis.com">
                    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200..800&family=Open+Sans:ital,wght@0,300..800;1,300..800&family=Urbanist:ital,wght@0,100..900;1,100..900&display=swap" rel="stylesheet">
                    <style>
                    #header, #footer {{ padding: 0 !important; }}
                    {inline_css}
                    </style>
                </head>
             <body>

        """

    print("Generating for FLOW: ", flow)
    if flow in [SessionFlowName.LoginMiStory, SessionFlowName.SsoFlow, SessionFlowName.GuestMiStory,
                SessionFlowName.Reflection, SessionFlowName.YLC]:
        html_content += get_first_page_html(
            profile=profile, project=project_to_pass, voice_provider=voice_provider, story=object_to_pass,
            story_vernacular=story_vernacular, flow=flow
        )
        html_content += get_story_secondpage_html(
            story=object_to_pass, project=project_to_pass, story_vernacular=story_vernacular
        )
        html_content += get_story_images_page_html(story=story, story_vernacular=story_vernacular)
        html_content += get_thirdpage_html(
            story=object_to_pass, profile=profile, project=project_to_pass, voice_provider=voice_provider,
            story_vernacular=story_vernacular, flow=flow
        )
    elif flow in [SessionFlowName.GuestDiscussion, SessionFlowName.LoginDiscussion]:
        html_content += get_mom_report_html(
            story=object_to_pass, story_vernacular=story_vernacular, profile=profile,
            voice_provider=voice_provider
        )
    else:
        html_content += get_common_report_html(
            story=object_to_pass, profile=profile, story_vernacular=story_vernacular
        )

    html_content += """
        <script>
        document.addEventListener("DOMContentLoaded", function () {
            function checkOverflowAndInsertBreaks() {
                const containers = document.querySelectorAll(".story-second-page-container");
                console.log("containers: ", containers)
                containers.forEach(container => {
                    if (container.scrollHeight > container.clientHeight) {
                        // Create a page break div if the content overflows
                        const pageBreak = document.createElement("div");
                        pageBreak.style.pageBreakBefore = "always";
                        container.parentNode.insertBefore(pageBreak, container.nextSibling);
                    }
                });
            }

            checkOverflowAndInsertBreaks(); // Run on page load
        });
        </script>
        </body>
    </html>
    """
    return html_content


def get_html_from_template(story, profile, flow, auth=False, language=None):
    project = Project.objects.filter(story=story).first()
    flow_obj = Flow.objects.get(flow_route=flow)

    language_used = language

    if language_used is None:
        chat_session = ChatSession.objects.filter(session=story.session).first()
        translation_languages = list(story.translations.values_list('language', flat=True))
        language_used = (
            chat_session.language or
            translation_languages[0] if translation_languages else
            (project.project_language if project else None) or
            story.language or
            'en'
        )

    story_serialized = StoryCreateSerializer(story)
    project_serialized = ProjectSerializer(project)
    profile_serialized = profile

    pdf_template: PDFTemplates | None = None
    if auth:
        pdf_template = PDFTemplates.objects.filter(
            flow=flow_obj, 
            user_type__in=[UserTypeChoices.AUTH, UserTypeChoices.ALL]
        ).first()
    else:
        pdf_template = PDFTemplates.objects.filter(flow=flow_obj,
            user_type__in=[UserTypeChoices.GUEST, UserTypeChoices.ALL]
        ).first()

    if pdf_template is None:
        return ""

    jinja_template = pdf_template.template
    constants = pdf_template.constants_json

    render_params = {
        "constants": constants.get(language_used, {}),
        "story": story_serialized.data,
        "project": project_serialized.data,
        "profile": profile_serialized
    }

    if language_used != StoryLanguageChoices.ENGLISH:
        translated_story = StoryTranslation.objects.select_related("story").get(story__session=story.session, language=language)
        render_params.get("story", {})["title"] = translated_story.title
        render_params.get("story", {})["content"] = translated_story.content
        render_params.get("story", {})["location"] = translated_story.location
        render_params.get("story", {})["other_params"] = translated_story.other_params

    template = Template(jinja_template)
    html_content = template.render(**render_params)
    return html_content

def update_story_pdf(access_token, session, flow, is_edit_story=False):

    try:
        chatsession = ChatSession.objects.values("language").get(session=session)

        story = Story.objects.get(session=session)
        translated_story = None
        if chatsession.get("language", StoryLanguageChoices.ENGLISH)  != StoryLanguageChoices.ENGLISH:
            translated_story = StoryTranslation.objects.select_related("story").get(story__session=session, language=chatsession.get("language", StoryLanguageChoices.ENGLISH))

        if translated_story is not None:
            story.title = translated_story.title
            story.content = translated_story.content
            story.location = translated_story.location
            story.other_params = translated_story.other_params

        if story and story.content and story.formatted_content:
            update_story_content(story)
        profile = story.author
        print("profile: ", profile)
        print("story: ", story.title)
        print("story format: ", story.formatted_content)
        language = chatsession.get("language", StoryLanguageChoices.ENGLISH)
        flow_obj = Flow.objects.filter(flow_route=flow).first()
        has_pdf_template = flow_obj and PDFTemplates.objects.filter(flow=flow_obj).exists()
        if has_pdf_template:
            html_content = get_html_from_template(
                story=story, profile=profile, flow=flow,
                auth=(profile is not None), language=language
            )
        else:
            html_content = get_story_html(story=story, profile=profile, flow=flow)

        pdf_generated = generate_pdf_with_gotenberg(html_content)
        # print("pdf_generated: ", pdf_generated)
        pdf_file_name = story.title
        if not pdf_file_name or pdf_file_name == '':
            pdf_file_name = 'Improvement_story'
        pdf_file_name = f"{pdf_file_name}.pdf"
        print("pdf_file_name: ", pdf_file_name)
        pdf_content = ContentFile(pdf_generated, name=pdf_file_name)
        print("pdf_content: ", pdf_content)
        print("pdf_content type: ", type(pdf_content))

        story_media = StoryMedia.objects.filter(story=story, media_type=MediaTypeChoices.PDF).first()

        story_media.name = pdf_file_name
        story_media.file.save(pdf_file_name, pdf_content)
        story_media.include_in_story = False
        story_media.save()
        logger.info("StoryMedia updated and saved successfully.")
        logger.info(f"Updated name: {story_media.name}")
        logger.info(f"Updated file path: {story_media.file}")
        logger.info(f"Include in story: {story_media.include_in_story}")
        logger.info(f"Public url: {story_media.get_public_url()}")
        chat_session = ChatSession.objects.get(session=session)
        project_id = chat_session.project_id

        if (access_token in [None, "", "null"] or not session or not project_id or
                flow not in[SessionFlowName.Reflection, SessionFlowName.GuestMiStory]):
            print("Not calling shikshalokam api as access_tokne or session or project_id is missing")
            return

        upload_response_json = upload_to_cloud(
            session_value=session, access_token=access_token, story=story
        )

        print("upload_response_json: ", upload_response_json)
        story_media_objects = StoryMedia.objects.filter(
            story=story, include_in_story=True
        ).exclude(media_type=MediaTypeChoices.PDF)
        attachments=[]
        if is_edit_story:
            existing_attachments = fetch_existing_project_attachments(project_id, access_token)
            print("existing_attachments: ", existing_attachments)
            if existing_attachments:
                attachments.extend(existing_attachments)

            attachments.extend([
                {
                    "name": media.name,
                    "sourcePath": media.source_path,
                    "type": media.media_type,
                    "page": "story"

                }
                for media in story_media_objects
            ])
        print("attachments: ", attachments)

        pdf_information = upload_response_json.get('pdfInformation')
        print("pdf_information: ", pdf_information)

        company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')
        ai_user = Profile.objects.get(id=1)

        if company_chats and company_chats[0].receiver != ai_user:
            company_chats.pop(0)
        conversation = get_stored_conversation(company_chats=company_chats)
        chat_history = get_stored_chathistory(company_chats=company_chats)


        tasks_payload = []

        task_id_from_session = None
        if chat_session.other_params:
            task_id_from_session = chat_session.other_params.get('task_id')

        if task_id_from_session:
            task_obj = Task.objects.filter(task_id=task_id_from_session).first()

            if task_obj:
                tasks_payload.append({
                    "_id": task_obj.task_id,
                    "status": task_obj.task_status,
                    "taskName": task_obj.task_name
                })
            else:
                tasks_payload.append({
                    "_id": task_id_from_session,
                    "status": "completed"
                })

        else:
            project = Project.objects.filter(project_id=project_id).first()
            if project:
                project_tasks = Task.objects.filter(project=project)

                for task in project_tasks:
                    tasks_payload.append({
                        "_id": task.task_id,
                        "status": task.task_status.lower() if task.task_status else None,
                        "taskName": task.task_name
                    })

        request_body = {
            "story": {
                "title": story.title,
                "objective": story.objective,
                "timeline": "",
                "actionSteps": story.action_steps or [],
                "resources": [],
                "impact": story.impact,
                "summary": story.content,
                "authorName": story.author.first_name if story.author else "",
                "location": story.location or "",
                "conversation": conversation,
                "chatHistory": chat_history,
                "attachments": attachments,
                "pdfInformation": pdf_information,
            },
            "tasks": tasks_payload
        }

        headers = {
            "X-auth-token": access_token,
        }
        print("Req body: ", request_body)
        if flow in [SessionFlowName.GuestMiStory]:
            url = f"https://{base_url}/userProjects/update/{project_id}"
            response = requests.post(url, headers=headers, json=request_body)
        else:
            url = f"https://{base_url}/userProjects/addStory/{project_id}"
            response = requests.put(url, headers=headers, json=request_body)

        print("Response: ", response.text)
        response.raise_for_status()

        print(f"Story successfully updated to Shikshalokam: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print("Failed to save story to Shikshalokam: %s", e)
        raise
    except Exception as e:
        print("An unexpected error occurred: %s", e)
        traceback.print_exc()
        raise


def update_story_content(story):
    try:
        formatted_data = json.loads(story.formatted_content)
    except (json.JSONDecodeError, TypeError):
        print("Invalid or missing formatted_content")
        return

    accumulated_text = ""
    for block in formatted_data:
        if block.get("type") == "paragraph" and "data" in block and "text" in block["data"]:
            # accumulated_text += block["data"]["text"] + "\n"
            plain_text = re.sub(r'<[^>]+>', '', block["data"]["text"])
            accumulated_text += plain_text + "\n"

    print("\nold content: ", story.content)
    print("\naccumulated_text: ", accumulated_text)
    story.content = accumulated_text.strip()
    story.save()
