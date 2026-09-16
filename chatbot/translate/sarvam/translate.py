import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from sarvamai import SarvamAI
import logging


logger = logging.getLogger('django')
sarvam_api_key = os.getenv("SARVAM_API_KEY")


def split_text_into_chunks_safely(text, max_chars=990):
    """
    Splits text into chunks under max_chars.
    Tries to split on sentence boundaries (., ?, !).
    Falls back to word-safe chunks if punctuation is missing.
    """
    chunks = []
    sentence_end_pattern = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_end_pattern.split(text)

    current_chunk = ""
    for sentence in sentences:
        if not sentence.strip():
            continue

        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(sentence) <= max_chars:
                current_chunk = sentence
            else:
                # Fallback to word-safe chunking if sentence too long
                words = sentence.split()
                word_chunk = ""
                for word in words:
                    if len(word_chunk) + len(word) + 1 <= max_chars:
                        word_chunk += (" " if word_chunk else "") + word
                    else:
                        chunks.append(word_chunk.strip())
                        word_chunk = word
                if word_chunk:
                    current_chunk = word_chunk
                else:
                    current_chunk = ""
    if current_chunk:
        chunks.append(current_chunk.strip())

    print(f"[Chunking] Total Chunks Created: {len(chunks)}")
    return chunks


def translate_chunk(client, chunk, source_lang, target_lang, gender, mode, output_script, enable_preprocessing):
    """
    Worker function for translating a single chunk.
    """
    try:
        response = client.text.translate(
            input=chunk,
            source_language_code=source_lang,
            target_language_code=target_lang,
            speaker_gender=gender,
            mode=mode,
            output_script=output_script,
            enable_preprocessing=enable_preprocessing,
        )
        logger.info(f"Response {response}")

        translated = response.translated_text if hasattr(response, 'translated_text') else chunk
        print(f"[Translate] Done. Translated length: {len(translated)}")

        return translated
    except Exception as e:
        logger.error('Error processing: %s', e, exc_info=True)
        print(f"Error translating chunk: {chunk[:30]}... - {str(e)}")
        return chunk


def sarvam_translate_text(voice_provider, input_text, source_lang, target_lang, gender, max_chars=990):
    try:
        client = SarvamAI(
            api_subscription_key=sarvam_api_key
        )
        mode="formal"
        output_script="fully-native"
        enable_preprocessing = True

        other_params = voice_provider.other_params
        if other_params:
            mode = other_params.get('mode')
            output_script = other_params.get('output_script')
            enable_preprocessing = other_params.get('enable_preprocessing')
            if enable_preprocessing:
                enable_preprocessing = str(other_params.get('enable_preprocessing', True)).lower() == 'true'

        chunks = split_text_into_chunks_safely(text=input_text, max_chars=max_chars)

        translated_chunks = [None] * len(chunks)
        print(f"[Translate] Submitting {len(chunks)} chunks for parallel translation...")

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    translate_chunk,
                    client,
                    chunks[i],
                    source_lang,
                    target_lang,
                    gender,
                    mode,
                    output_script,
                    enable_preprocessing
                ): i for i in range(len(chunks))
            }

            for future in as_completed(futures):
                index = futures[future]
                translated_chunks[index] = future.result()
                print(f"[Translate] Chunk {index+1}/{len(chunks)} completed.")

        final_translation = " ".join(translated_chunks)
        print("[Translate] All chunks translated and reassembled.")

        return {
            'status': 200,
            'content': final_translation
        }

    except Exception as e:
        logger.error('Error processing: %s', e, exc_info=True)
        print(f"Error during translation API call: {str(e)}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error during translation API call: {str(e)}"
        }
