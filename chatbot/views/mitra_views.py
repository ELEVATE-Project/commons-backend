import traceback
from chatbot.models import Profile, MediaTypeChoices
from chatbot.pdf.knowledge_service.project_report_pdf import generate_project_pdf
from chatbot.utils.shikshalokam_mitra_utils import create_project_utils, create_mitra_project_utils
from rest_framework.decorators import api_view
from rest_framework.response import Response
from chatbot.utils.media_preview.excel_service import generate_and_upload_excel
from chatbot.utils.project_formatting_utils import (
    normalize_sources_from_chunks,
    format_project_timeline
)
from chatbot.utils.media_preview.excel_service import (
    generate_excel_file,
)
from chatbot.utils.S3.s3_service import upload_media
from shikshalokam.models import Project



@api_view(['POST'])
def create_project_view(request):
    body = request.data
    access_token = body.get('access_token')
    session = body.get('session')
    user_problem_statement = body.get('user_problem_statement')
    user_action_steps = body.get('user_action_steps')
    project_duration = body.get('project_duration')
    project_title = body.get('project_title')
    project_objective = body.get('user_objective')
    profile_id = body.get('profile_id')
    chunks = body.get('chunks')
    language = body.get('language')

    sources_list = normalize_sources_from_chunks(chunks)
    timeline = format_project_timeline(project_duration)

    project_id = None
    program_id = None
    response = ""
    if access_token:
        if not chunks:
            return Response({
                'status': 'error',
                'message': 'Project source cant be empty',
            }, status=500)

        response = create_project_utils(
            access_token=access_token, user_problem_statement=user_problem_statement,
            user_action_steps=user_action_steps, project_title=project_title,
            project_duration_weeks=project_duration, chunks=chunks, session=session,
            project_objective=project_objective, status='started'
        )

        project_id = response.get('projectId')
        program_id = response.get('programId')

    profile = Profile.objects.filter(id=profile_id).first()

    result = create_mitra_project_utils(
        profile=profile,
        actual_problem_statement=user_problem_statement,
        project_title=project_title,
        project_duration=project_duration,
        project_objective=project_objective,
        user_action_steps=user_action_steps,
        project_id=project_id,
        program_id=program_id,
        chunks=chunks,
        language=language,
        session=session
    )

    pdf_url = None
    pdf_filename = "Project_Report.pdf"
    project_id = result.get('project_id') if not project_id else project_id
    try:
        author_name = profile.first_name if profile else ""
        location = profile.location if profile and hasattr(profile, '') else ""

        

        pdf_content = generate_project_pdf(
            project_title=project_title,
            author_name=author_name,
            location=location,
            problem_statement=user_problem_statement,
            objective=project_objective,
            timeline=timeline,
            action_steps=user_action_steps,
            sources=chunks,
            language=language,
            session=session
        )


        print("PDF report is generated successfully")

        if pdf_content and result.get('id'):
            pdf_filename = f"{project_title}.pdf" if project_title else "Project_Report.pdf"
            pdf_filename = "".join(
                c for c in pdf_filename if c.isalnum() or c in (' ', '-', '_', '.')
            ).replace(' ', '_')

            pdf_url = None

            if pdf_content and result.get("id"):
                pdf_media = upload_media(
                    project_id=result.get("id"),
                    media_type="pdf",
                    file_name=pdf_filename,
                    file_content=pdf_content.read(),
                    content_type="application/pdf",
                )

                if pdf_media:
                    pdf_url = pdf_media["url"]



        excel_generation_result = generate_excel_file(
            project_title=project_title,
            author_name=author_name,
            location=location,
            timeline=timeline,
            user_problem_statement=user_problem_statement,
            project_objective=project_objective,
            user_action_steps=user_action_steps,
            sources_list=sources_list,
        )

        excel_url = None
        excel_filename = None


        if excel_generation_result and result.get("id"):
            excel_media = upload_media(
                project_id=result.get("id"),
                media_type="excel",
                file_name=excel_generation_result["file_name"],
                file_content=excel_generation_result["file"].read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            if excel_media:
                excel_url = excel_media["url"]
                excel_filename = excel_media["file_name"]


    except Exception as e:
        print(f"Error generating/uploading PDF: {str(e)}")
        traceback.print_exc()


    media_response = []
    if pdf_url:
        media_response.append({
            'media_type': MediaTypeChoices.PDF,
            'url': pdf_url,
            'file_name': pdf_filename
        })

    if excel_url:
        media_response.append({
            'media_type': MediaTypeChoices.XLSX,
            'url': excel_url,
            'file_name': excel_filename
        })

    if not media_response:
        media_response.append({
            'media_type': MediaTypeChoices.PDF,
            'url': '',
            'file_name': pdf_filename
        })


    return Response({
        'status': 'ok',
        'result': response,
        'project_id': project_id,
        'mitra_result': result,
        'media': media_response
    }, status=200)
