import os

import requests
from pydantic_core._pydantic_core import ValidationError

from chatbot.models import Profile, Company
from chatbot.models.geo_models import ProfileAddress
from chatbot.serializer.profile_serializer import ProfileSerializer

base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def create_profile_utils(access_token):

    try:
        json_response = get_profile_detail(access_token=access_token)

        if not json_response or "result" not in json_response:
            return json_response

        result = json_response.get("result")
        email = result.get('email')
        userid = result.get('id')
        name = result.get('name')
        preferred_language = result.get('preferred_language', {}).get('value')
        organization = result.get('organization', {}).get('name')
        block = result.get('block', {}).get('label')
        state = result.get('state', {}).get('label')
        district = result.get('district', {}).get('label')
        user_roles = result.get('user_roles', [])


        company = Company.objects.get(slug='shikshalokamstaging')
        profile_data = {
            "email": email,
            "first_name": name,
            "preferred_route": preferred_language,
            "org_associated": organization,
            "password": 'grit@123',
            "company": company,
            "designation": user_roles
        }

        address_data = {
            "block": block,
            "state": state,
            "district": district,
        }
        profile, created = Profile.objects.update_or_create(
            userid=userid,
            defaults=profile_data
        )

        if address_data:
            ProfileAddress.objects.filter(profile=profile).delete()

            ProfileAddress.objects.update_or_create(
                profile=profile,
                defaults=address_data
            )
        serialized_profile = ProfileSerializer(profile).data
        return {
            'success': True,
            'data': serialized_profile
        }
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")
        return {
            'success': False,
            'status_code': 500,
            'message': f"Error while making the API call: {e}"
        }
    except Exception as e:
        print("e: ", e)
        return {
            'success': False,
            'status_code': 500,
            'message': f"An unexpected error occurred: {e}"
        }


def get_profile_detail(access_token):
    url = f"https://{base_url}/profile/read"

    headers = {
        "X-auth-token": access_token,
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 401:
            return {
                'success': False,
                'status_code': 401,
                'message': 'Access token is invalid or expired.'
            }
        elif response.status_code != 200:
            return {
                'success': False,
                'status_code': response.status_code,
                'message': f"API returned an error: {response.text}"
            }

        json_response = response.json()

        if not json_response or "result" not in json_response:
            return {
                'success': False,
                'status_code': 400,
                'message': 'Invalid response from the API.'
            }
        return json_response

    except Exception as e:
        return {
            'success': False,
            'status_code': 500,
            'message': f"An unexpected error occurred: {e}"
        }
