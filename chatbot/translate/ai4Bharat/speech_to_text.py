import base64
import os
import traceback
import requests
import json_repair
import concurrent.futures
import logging
from chatbot.translate.base.speech_to_text import split_audio


logger = logging.getLogger('django')
ai4bharat_api_key = os.getenv("BHASHANI_API_KEY")
ai4bharat_base_url = os.getenv("BHASHANI_BASE_URL")
ai4bharat_user_id = os.getenv("BHASHANI_USER_ID")
ai4bharat_authorization = os.getenv("BHASHANI_AUTHORIZATION")


def transcribe_single_chunk(chunk_number, chunk, audio_format, source_language, voice_provider):
    b64_chunk = base64.b64encode(chunk).decode('utf-8')
    response = ai4bharat_speech_text(
        base64=b64_chunk,
        audio_format=audio_format,
        source_language=source_language,
        voice_provider=voice_provider
    )
    logger.info(f"response: {response}")
    if response['status'] == 200:
        return (chunk_number, response['content'])
    else:
        return (chunk_number, '')


def transcribe_ai4bharat_multiple_chunks(voice_provider, base64_audio_file, source_language, audio_format):
    try:
        audio_bytes = base64.b64decode(base64_audio_file)
        duration = 10
        if voice_provider.other_params:
            duration = int(voice_provider.other_params.get('chunk_duration', 10))
        chunks = split_audio(audio_bytes, chunk_duration=duration)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    transcribe_single_chunk, chunk_number, chunk, audio_format, source_language,
                    voice_provider
                )
                for chunk_number, chunk in chunks
            ]
            transcripts = [future.result() for future in concurrent.futures.as_completed(futures)]
            transcripts.sort()

        transcript = " ".join(content for _, content in transcripts)
        return {'status': 200, 'content': transcript}

    except Exception as e:
        logger.error('Error processing file: %s', e, exc_info=True)
        traceback.print_exc()
        return {'status': 500, 'content': str(e)}



def ai4bharat_speech_text(voice_provider, base64, audio_format, source_language):
    try:
        other_params = voice_provider.other_params if voice_provider.other_params else {}

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {
                            "sourceLanguage": source_language,
                        },
                        "serviceId": other_params.get('serviceId', "bhashini/iitm/asr-dravidian--gpu--t4"),
                        "audioFormat": audio_format,
                        "samplingRate": int(other_params.get('samplingRate', 16000)) if isinstance(
                            other_params.get('samplingRate'), int) or str(
                            other_params.get('samplingRate')).isdigit() else 16000,
                        "preProcessors": other_params.get('preProcessors') if isinstance(
                            other_params.get('preProcessors'), list) else [],
                        "postProcessors": other_params.get('postProcessors') if isinstance(
                            other_params.get('postProcessors'), list) else [],

                    }
                }
            ],
            "inputData": {
                "audio": [
                    {
                        "audioContent": base64
                    }
                ]
            }
        }

        headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'Authorization': ai4bharat_authorization,
            'userID': ai4bharat_user_id,
            'ulcaApiKey': ai4bharat_api_key
        }
        response = requests.post(ai4bharat_base_url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            print("response: ", response.text)
            audio_data = json_repair.repair_json(response.text, return_objects=True)
            if isinstance(audio_data, dict) and 'pipelineResponse' in audio_data:
                audio_content = audio_data['pipelineResponse'][0].get('output', [{}])[0].get('source', '')
                print("TRANSCRIPT: ", audio_content)
                return {
                    'status': 200,
                    'content': audio_content
                }
            else:
                return {
                    'status': 500,
                    'content': 'Unexpected response format from AI4Bharat API'
                }
        else:
            print("Error in response: ", response.text)
            return {
                'status': response.status_code,
                'content': 'Failed to fetch audio from AI4Bharat API'
            }

    except Exception as e:
        logger.error('Error processing file: %s', e, exc_info=True)
        traceback.print_exc()
        return {
            'status': 500,
            'content': str(e)
        }
