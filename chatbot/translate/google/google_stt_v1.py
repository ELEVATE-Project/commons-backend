import traceback
from typing import List
from google.cloud import speech
from google.cloud.speech_v1 import types
import base64


def transcribe_multiple_languages_v1(
    language_codes: List[str],
    audio_file: str,
) -> dict:
    client = speech.SpeechClient()

    try:

        audio_bytes = base64.b64decode(audio_file)

        audio = speech.RecognitionAudio(content=audio_bytes)
        config = types.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            # sample_rate_hertz=16000,
            language_code=language_codes[0],
            alternative_language_codes=language_codes[1:] if len(language_codes) > 1 else [],
            model="default",
        )

        try:
            operation = client.long_running_recognize(config=config, audio=audio)
            response = operation.result(timeout=600)
            if not response or not response.results:
                print("No response or results received.")
                return {'status': 500, 'content': "No transcription results."}

        except Exception as e:
            print(f"Error during API request: {e}")
            traceback.print_exc()
            return {
                'status': 500,
                'content': f"Error during API request: {e}"
            }
        if not response or isinstance(response, str):
            print("response: ", response)
        transcripts = []
        for res_result in response.results:
            if not res_result.alternatives:
                continue
            transcript = res_result.alternatives[0].transcript
            transcripts.append(transcript)
            print(f"Transcript: {transcript}")

        print("transcripts: ", transcripts)
        full_transcript = " ".join(transcripts)
        print("full_transcript: ", full_transcript)
        return {
            'status': 200,
            'content': full_transcript
        }

    except Exception as e:
        print(f"Error processing file: {e}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error processing file: {e}"
        }
