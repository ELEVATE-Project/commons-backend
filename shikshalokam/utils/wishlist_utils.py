import os
import requests


base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def add_project_wishlist(project, access_token):
    url = f"https://{base_url}/wishlist/add/{project.id}"

    headers = {
        "X-auth-token": access_token,
    }
    title = project.actual_title if project.actual_title else project.expected_title
    objective = project.actual_objective if project.actual_objective else project.expected_objective
    duration = project.actual_duration if project.actual_duration else project.expected_duration
    request_body = {
        "title": title,
        "referenceFrom": project.generated_by,
        "description": objective,
        "metaInformation": {
            "duration": duration
        }
    }

    print("req body: ", request_body)

    try:
        response = requests.post(url, headers=headers, json=request_body)
        response.raise_for_status()
        json_response = response.json()
        print("json_response: ", json_response)

        return json_response

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")
        return None
    except ValueError as e:
        print(f"Validation error: {e}")
        return None


def remove_project_wishlist(project, access_token):
    url = f"https://{base_url}/wishlist/remove/{project.id}"

    headers = {
        "X-auth-token": access_token,
    }

    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        json_response = response.json()
        print("json_response: ", json_response)

        return json_response

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")
        return None
    except ValueError as e:
        print(f"Validation error: {e}")
        return None

