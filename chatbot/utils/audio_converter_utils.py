import os
import uuid
import base64
import requests
import subprocess
from tempfile import NamedTemporaryFile
import logging
from django.conf import settings

from chatbot.services.storage import StorageFactory


logger = logging.getLogger('django')


def convert_s3_audio_to_wav_base64(s3_url: str) -> str:
    try:
        storage_handler = StorageFactory.get_storage_handler()

        audio_bytes = None
        if s3_url.startswith("https://"):
            response = requests.get(s3_url)
            response.raise_for_status()
            audio_bytes = response.content

        else:
            audio_bytes = storage_handler.get_file_from_store(object_url=s3_url)


        # Step 2: Save original audio to temp file
        input_ext = s3_url.split('.')[-1]
        logger.info("input_ext: %s", input_ext)

        input_ext = 'opus'
        with NamedTemporaryFile(suffix=f".{input_ext}", delete=False) as input_file:
            input_file.write(audio_bytes)
            input_path = input_file.name
        logger.info("Saved input audio to temporary file: %s", input_path)

        # Step 3: Define output WAV file path
        output_path = f"/tmp/{uuid.uuid4().hex}.wav"
        logger.info("Output WAV will be saved to: %s", output_path)

        # Step 4: Convert using FFmpeg
        ffmpeg_command = [
            'ffmpeg',
            '-y',
            '-i', input_path,
            '-ac', '1',
            '-ar', '16000',
            output_path
        ]
        subprocess.run(ffmpeg_command, check=True)
        logger.info("FFmpeg conversion successful")


        # Step 5: Read WAV bytes
        with open(output_path, 'rb') as f:
            wav_bytes = f.read()
        logger.info("WAV file read successfully.")

        encoded_audio = base64.b64encode(wav_bytes).decode('utf-8')
        logger.info("WAV file encoded to base64")

        return encoded_audio

    finally:
        # Clean up temporary files
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)
            logger.info(f"Deleted temporary input file: %s", input_path)

        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)
            logger.info(f"Deleted temporary output file: %s", output_path)
