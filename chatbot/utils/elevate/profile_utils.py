import os
import requests
from chatbot.models import Profile, Company, SessionFlowName
from chatbot.models.geo_models import ProfileAddress
import json_repair

elevate_base_url = os.getenv('ELEVATE_BASE_URL')

def handle_elevate_profile(access_token):
    try:
        url = f"{elevate_base_url}/user/v1/user/read"
        headers = {
            'X-auth-token': access_token
        }
        response = requests.get(url=url, headers=headers)
        print("Read status: ", response.status_code)
        response.raise_for_status()

        json_data = response.json()
        print(json_data)

        if json_data.get('responseCode', '').lower() != 'ok':
            print("Unexpected response code:", json_data.get('responseCode'))
            return {}

        user_data = json_data.get('result', {})
        full_name = user_data.get('name', '')
        first_name, last_name = (full_name.split(' ', 1) + [''])[:2]
        phone = user_data.get('phone')
        email = user_data.get('email')
        language = user_data.get('preferred_language')
        raw_designation = user_data.get('professional_role')
        designation_value = None
        if isinstance(raw_designation, dict):
            designation_value = raw_designation.get('label') or raw_designation
        elif isinstance(raw_designation, str):
            try:
                designation_value = json_repair.repair_json(raw_designation, return_objects=True)
                if isinstance(designation_value, dict):
                    designation_value = designation_value.get('label')
            except Exception:
                designation_value = raw_designation
        else:
            designation_value = None

        if language:
            if isinstance(language, dict):
                language = language.get('value', 'en')
            else:
                language = user_data.get('preferred_language')
        else:
            language = 'en'

        company = Company.objects.filter(slug='shikshalokamstaging').first()

        if (not email or email == '') and phone and phone != '':
            email = f"{phone}@shikshalokam.org"

        if not email or email == '':
            print("No valid email or phone found to generate email.")
            return {}

        profile, _ = Profile.objects.update_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'phone': user_data.get('phone'),
                'status': user_data.get('status', 'ACTIVE'),
                'company': company,
                'password': "grit@123",
                'latest_flow_used': SessionFlowName.LoginMiStory,
                'location': user_data.get('location'),
                'designation': designation_value,
                'other_params': {'elevate_profile_details': user_data},
                'source': 'elevate',
                'preferred_route': language,
            }
        )

        state = user_data.get('state', {})
        district = user_data.get('district', {})
        block = user_data.get('block', {})

        if state.get('label') or district.get('label') or block.get('label'):
            ProfileAddress.objects.update_or_create(
                profile=profile,
                defaults={
                    'state': state.get('label'),
                    'district': district.get('label'),
                    'block': block.get('label'),
                }
            )
            print("ProfileAddress updated or created successfully")

        profile_address = ProfileAddress.objects.filter(profile=profile).first()

        profile_response = {
            "first_name": profile.first_name,
            "company": profile.company.slug if profile.company else None,
            "state": profile_address.state if profile_address else None,
            "has_accepted_tnc": "ONGOING",
            "route": profile.preferred_route,
            "profileid": profile.id,
            'reroute_url': os.getenv('SSO_REROUTE_URL')
        }
        return profile_response

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return {}
