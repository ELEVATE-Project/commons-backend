import traceback
from typing import List
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.api_core.client_options import ClientOptions
import base64
import concurrent.futures
import logging

from chatbot.translate.base.speech_to_text import is_silent_chunk, split_audio

logger = logging.getLogger('django')


def transcribe_chunk(client, project_id, location, config, chunk_number, chunk):
    """Transcribes a single chunk of audio."""
    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{project_id}/locations/{location}/recognizers/_",
        config=config,
        content=chunk,
    )
    try:
        response = client.recognize(request=request)
        transcript = ""
        if response and not isinstance(response, str):
            print("response: ", response)
            for res_result in response.results:
                print("res_result: ", res_result)
                if res_result and res_result.alternatives:
                    transcript += res_result.alternatives[0].transcript + " "
        return (chunk_number, transcript.strip())
    except Exception as e:
        logger.error(
            'Error during API request for chunk %s : %s | location=%s recognizer=%s',
            chunk_number,
            e,
            location,
            request.recognizer,
            exc_info=True,
        )
        traceback.print_exc()
        return (chunk_number, "")


def transcribe_multiple_languages_v2(
        project_id: str,
        language_codes: List[str],
        audio_file: str,
        voice_provider: any
) -> dict:

    try:
        other_params = voice_provider.other_params or {}
        location = other_params.get("location", "global")

        client_options = None

        if location != "global":
            client_options = ClientOptions(
                api_endpoint=f"{location}-speech.googleapis.com"
            )

        client = SpeechClient(client_options=client_options)

        config_kwargs = {
            "auto_decoding_config": cloud_speech.AutoDetectDecodingConfig(),
            "language_codes": language_codes,
            "model": other_params.get("model", "latest_long"),
        }

        # -------- FEATURES --------
        features_kwargs = {}

        feature_params = [
            "enable_automatic_punctuation",
            "enable_spoken_punctuation",
            "enable_spoken_emojis",
            "enable_word_time_offsets",
            "profanity_filter",
            "max_alternatives"
        ]

        for param in feature_params:
            if param in other_params:
                features_kwargs[param] = other_params[param]

        if features_kwargs:
            config_kwargs["features"] = cloud_speech.RecognitionFeatures(**features_kwargs)

        # -------- BOOST WORDS --------
        if other_params.get("boost_words"):

            phrases = []

            for item in other_params["boost_words"]:
                if isinstance(item, dict):
                    word = item.get("word")
                else:
                    word = item

                if word:
                    phrases.append({"value": word})

            config_kwargs["adaptation"] = {
                "phrase_sets": [
                    {
                        "inline_phrase_set": {
                            "phrases": phrases
                        }
                    }
                ]
            }

        config = cloud_speech.RecognitionConfig(**config_kwargs)

        audio_bytes = base64.b64decode(audio_file)
        duration = int(other_params.get('chunk_duration', 10))
        chunks = split_audio(audio_bytes, chunk_duration=duration)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_chunk = {
                executor.submit(
                    transcribe_chunk, client, project_id, location, config, chunk_number, chunk
                ): chunk_number
                for chunk_number, chunk in chunks
            }

            results = []
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_number, transcript = future.result()
                results.append((chunk_number, transcript))

        results.sort()  # Ensure correct order
        full_transcript = " ".join(transcript for _, transcript in results)

        return {'status': 200, 'content': full_transcript}

    except Exception as e:
        logger.error('Error processing file: %s', e, exc_info=True)
        traceback.print_exc()
        return {'status': 500, 'content': f"Error processing file: {e}"}
