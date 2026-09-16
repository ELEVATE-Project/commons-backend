import os
import traceback
import requests
import logging


ai4bharat_api_key = os.getenv("BHASHANI_API_KEY")
ai4bharat_base_url = os.getenv("BHASHANI_BASE_URL")
ai4bharat_user_id = os.getenv("BHASHANI_USER_ID")
ai4bharat_authorization = os.getenv("BHASHANI_AUTHORIZATION")
logger = logging.getLogger('django')


def call_ai4bharat_translation_api(voice_provider, source_language, target_language, message_body):
    api_url = ai4bharat_base_url

    other_params = voice_provider.other_params if voice_provider.other_params else {}

    payload = {
        "pipelineTasks": [
            {
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage": source_language,
                        "targetLanguage": target_language,
                    },
                    "serviceId": other_params.get('serviceId', 'bhashini/iiith/nmt-all'),
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
        response = requests.post(api_url, json=payload, headers=headers, timeout=60)
        print("Response: ", response)
        print("Res text: ", response.json())
        logger.info(f"Response from AI4Bharat Text Translation {response}")
        logger.info(f"JSON Response from AI4Bharat Text Translation {response.json()}")

        if response.status_code == 200:
            translated_data = response.json()
            if isinstance(translated_data, dict) and 'pipelineResponse' in translated_data:
                translated_message = translated_data['pipelineResponse'][0].get('output', [{}])[0].get('target', '')

                print("translated_message: ", translated_message)
                return {
                    'status': 200,
                    'content': translated_message
                }
        return {
            'status': 200,
            'content': message_body
        }
    except Exception as e:
        logger.error('Error processing: %s', e, exc_info=True)
        print(f"Error during translation API call: {str(e)}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error during translation API call: {str(e)}"
        }
