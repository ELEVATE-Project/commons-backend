import os
import traceback
import requests

ai4bharat_api_key = os.getenv("BHASHANI_API_KEY")
ai4bharat_base_url = os.getenv("BHASHANI_BASE_URL")
ai4bharat_user_id = os.getenv("BHASHANI_USER_ID")
ai4bharat_authorization = os.getenv("BHASHANI_AUTHORIZATION")


def call_ai4bharat_text_lang_detect_api(message_body):
    api_url = ai4bharat_base_url

    payload = {
    "pipelineTasks": [
        {
            "taskType": "txt-lang-detection",
            "config": {
                "serviceId": "bhashini/iiiith/indic-lang-detection-all"
            }
        }
    ],
    "inputData": {
        "input": [
            {
                "source": message_body
            }
        ]
    }
}

    headers = {
        'accept': '*/*',
        'content-type': 'application/json',
        'Authorization': ai4bharat_authorization,
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        print("Response: ", response)
        print("Res text: ", response.json())
        if response.status_code == 200:
            lang_detect_data = response.json()
            if isinstance(lang_detect_data, dict) and 'pipelineResponse' in lang_detect_data:
                lang_detect_message = (lang_detect_data['pipelineResponse'][0].get('output', [{}])[0].
                                           get('langPrediction', [{}])[0].get('langCode', 'en'))

                print("lang_detect_message: ", lang_detect_message)
                return {
                    'status': 200,
                    'content': lang_detect_message
                }
        return {
            'status': 200,
            'content': message_body
        }
    except Exception as e:
        print(f"Error during language detect API call: {str(e)}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error during language detect API call: {str(e)}"
        }
