import base64
import io
import os
from openai import OpenAI
import logging
from chatbot.translate.base.speech_to_text import split_audio

logger = logging.getLogger('django')


def transcribe_audio(
        base64_audio: str,
        audio_format: str,
        source_language: str,
        voice_provider: any
) -> dict:

    try:

        client_api_key = os.getenv("OPENAI_API_KEY")
        print("client_api_key: ", client_api_key)
        client = OpenAI(api_key=client_api_key)

        other_params = voice_provider.other_params or {}

        model = other_params.get("model", "whisper-1")
        response_format = other_params.get("response_format", "text")
        temperature = other_params.get("temperature", 0)
        chunk_duration = int(other_params.get("chunk_duration", 300))
        dictionary = other_params.get("dictionary", [])

        dictionary_prompt = None
        if dictionary and len(dictionary)> 0:
            dictionary_prompt = "Vocabulary: " + ", ".join(dictionary)

        audio_bytes = base64.b64decode(base64_audio)
        print("Audio size:", len(audio_bytes))
        # -------- CHUNK AUDIO --------
        chunks = split_audio(audio_bytes, chunk_duration=chunk_duration)
        print("Number of chunks:", len(chunks))
        transcripts = []

        for chunk_number, chunk in chunks:
            print("Sending chunk:", chunk_number, "size:", len(chunk))

            audio_file = io.BytesIO(chunk)
            audio_file.name = f"audio.{audio_format}"

            params = {
                "model": model,
                "file": audio_file,
                "response_format": response_format,
                "temperature": temperature,
            }

            if source_language:
                params["language"] = source_language

            if dictionary_prompt:
                params["prompt"] = dictionary_prompt

            transcription = client.audio.transcriptions.create(**params)
            print("transcription: ", transcription)

            if isinstance(transcription, str):
                transcripts.append(transcription)
            else:
                transcripts.append(str(transcription))

        full_transcript = " ".join(transcripts)

        return {
            "status": 200,
            "content": full_transcript
        }

    except Exception as e:
        logger.error("Error processing file: %s", e, exc_info=True)

        return {
            "status": 500,
            "content": f"Error during API request: {e}"
        }
