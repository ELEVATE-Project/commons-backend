"""Synthesizes speech from the input string of text or ssml.
Make sure to be working in a virtual environment.

Note: ssml must be well-formed according to:
    https://www.w3.org/TR/speech-synthesis/
"""
import base64
import traceback
from google.cloud import texttospeech

from chatbot.models import GenderChoices


def google_text_to_speech(message, language_code, voice_provider):
    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=message)
        gender_mapping = {
            GenderChoices.MALE: texttospeech.SsmlVoiceGender.MALE,
            GenderChoices.FEMALE: texttospeech.SsmlVoiceGender.FEMALE
        }
        gender_value = voice_provider.gender if voice_provider else None
        ssml_gender = gender_mapping.get(gender_value, texttospeech.SsmlVoiceGender.NEUTRAL)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code, ssml_gender=ssml_gender, name=voice_provider.name
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=voice_provider.voice_speed
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_content = response.audio_content
        audio_base64 = base64.b64encode(audio_content).decode("utf-8")

        return {
            'status': 200,
            'content': audio_base64
        }

    except Exception as e:
        print(f"Error while processing: {e}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error while processing: {e}"
        }
