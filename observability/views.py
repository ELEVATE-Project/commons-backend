from rest_framework.decorators import api_view
from chatbot.models import CompanyBot
from rest_framework.response import Response
from observability.models import CompanyBotTCRun
# from django.shortcuts import render


@api_view(['GET'])
def test_prompt_view(req, pk):
    try:
        test_case = CompanyBotTCRun(company_bot=CompanyBot(pk=pk))
        test_case.save()

        return Response({
            'status': 'ok',
        }, status=200)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=500)
