import base64
import os
import tempfile
import traceback
import concurrent.futures
from chatbot.translate.google.google_stt import split_audio
from sarvamai import SarvamAI
import logging


sarvam_api_key = os.getenv("SARVAM_API_KEY")
logger = logging.getLogger('django')


def transcribe_single_chunk(
        client, chunk_number, chunk, audio_format, source_language, model, mode
):

    try:
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=True) as tmp_file:
            tmp_file.write(chunk)
            tmp_file.flush()

            with open(tmp_file.name, "rb") as f:
                params = {
                    "file": f,
                    "model": model,
                    "language_code": source_language,
                }

                if mode:
                    params["mode"] = mode

                response = client.speech_to_text.transcribe(**params)
        print("response: ", response)
        if hasattr(response, "transcript"):
            return (chunk_number, response.transcript)

        return (chunk_number, "")

    except Exception:
        traceback.print_exc()
        return (chunk_number, "")


def transcribe_sarvam_multiple_chunks(
        voice_provider,
        base64_audio_file,
        source_language,
        audio_format="wav",
):

    try:

        other_params = voice_provider.other_params or {}

        duration = int(other_params.get("chunk_duration", 10))
        model = other_params.get("model", "saaras:v3")
        mode = other_params.get("mode", "transcribe")

        audio_bytes = base64.b64decode(base64_audio_file)

        chunks = split_audio(audio_bytes, chunk_duration=duration)
        client = SarvamAI(api_subscription_key=sarvam_api_key)

        with concurrent.futures.ThreadPoolExecutor() as executor:

            futures = [
                executor.submit(
                    transcribe_single_chunk, client, chunk_number, chunk, audio_format,
                    source_language, model, mode
                )
                for chunk_number, chunk in chunks
            ]

            transcripts = [
                future.result()
                for future in concurrent.futures.as_completed(futures)
            ]

        transcripts.sort()

        transcript = " ".join(content for _, content in transcripts)

        return {"status": 200, "content": transcript}

    except Exception as e:
        logger.error("Error processing: %s", e, exc_info=True)
        traceback.print_exc()

        return {"status": 500, "content": str(e)}

