from rest_framework.decorators import api_view
from django.http import HttpResponse
from chatbot.models import Story, ChatSession
from chatbot.utils.gotenberg_utils import generate_pdf_with_gotenberg
from chatbot.utils.shikshalokam_story_utils import get_story_html, get_html_from_template
from django.core.files.base import ContentFile


@api_view(['GET'])
def generate_pdf_view(request):
    body = request.query_params
    session = body.get("session")
    flow = body.get('flow')
    print("session: ", session)
    story = Story.objects.get(session=session)
    profile = story.author

    html_content = get_story_html(story=story, profile=profile, flow=flow)
    print("--------------------")
    print(html_content)
    print("--------------------")
    pdf_generated =  generate_pdf_with_gotenberg(html_content)
    pdf_file_name = f"Sample.pdf"
    pdf_content = ContentFile(pdf_generated, name=pdf_file_name)
    print("pdf_content: ", pdf_content)
    print("pdf_content type: ", type(pdf_content))
    # if pdf_generated:
    #     http_response = HttpResponse(pdf_generated, content_type="application/pdf")
    #     http_response["Content-Disposition"] = 'inline; filename="output.pdf"'
    #     return http_response
    # else:
    #     return HttpResponse("Error generating pdf!", status=500)

    return HttpResponse(html_content, content_type="text/html", status=200)


@api_view(['GET'])
def generate_pdf_view_v2(request):
    body = request.query_params
    session = body.get("session")
    flow = body.get('flow')
    print("session: ", session)
    story = Story.objects.get(session=session)
    chatsession = ChatSession.objects.get(session=session)
    profile = story.author

    html_content = get_html_from_template(story=story, profile=profile, flow=flow, language=chatsession.language)
    print("--------------------")
    print(html_content)
    print("--------------------")
    pdf_generated =  generate_pdf_with_gotenberg(html_content)
    pdf_file_name = f"Sample.pdf"
    pdf_content = ContentFile(pdf_generated, name=pdf_file_name)
    print("pdf_content: ", pdf_content)
    print("pdf_content type: ", type(pdf_content))

    return HttpResponse(html_content, content_type="text/html", status=200)