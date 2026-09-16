import io
import traceback
import wave
from pydub import AudioSegment
import logging

logger = logging.getLogger('django')


def is_silent_chunk(audio_bytes: bytes, format="wav", silence_thresh_dbfs=-40):
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=format)
        return audio.dBFS < silence_thresh_dbfs
    except Exception:
        traceback.print_exc()
        return False

def split_audio(audio_bytes, chunk_duration=10):
    """
    Splits audio into strictly 50-second chunks and skips silent ones.
    """
    with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        frame_rate = wf.getframerate()
        num_channels = wf.getnchannels()
        samp_width = wf.getsampwidth()
        total_frames = wf.getnframes()
        chunk_frames = chunk_duration * frame_rate  # Frames per 50s chunk

        chunks = []
        i = 0
        chunk_number = 0

        while i < total_frames:
            remaining_frames = total_frames - i
            chunk_size = min(chunk_frames, remaining_frames)

            wf.setpos(i)
            chunk_data = wf.readframes(chunk_size)

            output = io.BytesIO()
            with wave.open(output, "wb") as chunk_wf:
                chunk_wf.setnchannels(num_channels)
                chunk_wf.setsampwidth(samp_width)
                chunk_wf.setframerate(frame_rate)
                chunk_wf.writeframes(chunk_data)

            chunk_audio_bytes = output.getvalue()
            if is_silent_chunk(chunk_audio_bytes):
                logger.info(f"Skipping silent chunk {chunk_number}")
            else:
                chunk_seconds = chunk_size / frame_rate
                chunk_kb = len(chunk_audio_bytes) / 1024
                logger.info("Chunk %s: %.2f sec, %.2f KB", chunk_number, chunk_seconds, chunk_kb)

                chunks.append((chunk_number, chunk_audio_bytes))

            # chunk_seconds = chunk_size / frame_rate
            # chunk_kb = len(output.getvalue()) / 1024
            # logger.info("Chunk %s: %.2f sec, %.2f KB", chunk_number, chunk_seconds, chunk_kb)

            # chunks.append((chunk_number, output.getvalue()))
            i += chunk_size
            chunk_number += 1

    return chunks
