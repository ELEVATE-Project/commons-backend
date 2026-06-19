import json
import os
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response
import json_repair


location_auth = os.getenv('LOCATION_AUTH')
location_base_url = os.getenv('LOCATION_BASE_URL')


@api_view(['GET'])
def get_location_view(request):

    params = request.query_params

    parent_id = params.get('parentId')

    url = location_base_url

    filters = {"parentId": parent_id} if parent_id else {"type": "state"}

    payload = json.dumps({
        "request": {
            "filters": filters
        }
    })
    headers = {
        'Authorization': f'Bearer ' + location_auth,
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    print("res: ", response)
    json_response = response.json()
    print("json_response: ", json_response)
    location_list = json_response.get('result').get('response')

    return Response({
        'status': 'ok',
        'list': location_list
    }, status=200)


@api_view(['GET'])
def get_ip_location_view(request):
    try:
        #Gget the user's real IP address from headers
        ip = None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]  # get the first IP if multiple

        # Fall back to default IP if IP isn't found
        if not ip:
            return Response({
                'status': 'error',
                'message': 'Failed! No ip found.'
            })

        print("Client IP:", ip)

        url = f"http://ip-api.com/json/{ip}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            location_data = response.json()

            location_output = json_repair.repair_json(json.dumps(location_data), return_objects=True)

            return Response({
                'status': 'ok',
                'location': location_output
            }, status=200)
        else:
            return Response({
                'status': 'error',
                'message': 'Failed to fetch location'
            }, status=response.status_code)

    except Exception as e:
        print("Error occurred:", e)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=500)
