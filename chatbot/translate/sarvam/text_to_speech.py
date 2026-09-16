import os
import traceback
import requests
import re

from chatbot.models import LanguageMapping


def sarvam_text_to_speech(message, source_language, voice_provider):
    try:
        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            return {
                'status': 500,
                'content': 'SARVAM_API_KEY is not configured'
            }

        other = voice_provider.other_params if voice_provider and voice_provider.other_params else {}

        requested_speaker = other.get("speaker")

        # Guard against values like od-IN / en-IN mistakenly saved in name or speaker.
        if not requested_speaker and voice_provider and voice_provider.name:
            name_value = voice_provider.name.strip().lower()
            if not re.fullmatch(r"[a-z]{2,3}-[a-z]{2}", name_value):
                requested_speaker = name_value

        payload = {
            "text": message,
            "target_language_code": LanguageMapping.get_sarvam_language(source_language),
            "model": other.get("model", "bulbul:v3"),
            "speaker": requested_speaker or "shubh",
            "speech_sample_rate": other.get("speech_sample_rate", 24000),
            "output_audio_codec": other.get("output_audio_codec", "wav"),
            "pace": other.get("pace", 1.0),
            "temperature": other.get("temperature", 0.6),
        }

        response = requests.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )

        if response.status_code != 200:
            return {
                'status': response.status_code,
                'content': response.text
            }

        body = response.json()
        audios = body.get("audios", [])
        if not audios:
            return {
                'status': 500,
                'content': 'No audio returned from Sarvam TTS'
            }

        return {
            'status': 200,
            'content': audios[0]
        }

    except Exception as e:
        traceback.print_exc()
        return {
            'status': 500,
            'content': str(e)
        }
