import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from sarvamai import SarvamAI


logger = logging.getLogger("django")


class SarvamLanguageService:
    def __init__(self, api_key=None, max_workers=5):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        self.client = SarvamAI(api_subscription_key=self.api_key)
        self.max_workers = max_workers

    @staticmethod
    def split_text_into_chunks(text, max_chars=990):
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

        logger.info(f"[Chunking] Total Chunks Created: {len(chunks)}")
        return chunks

    def _process_in_parallel(self, chunks, worker_func):
        results = [None] * len(chunks)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(worker_func, chunks[i]): i
                for i in range(len(chunks))
            }

            for future in as_completed(futures):
                index = futures[future]
                results[index] = future.result()

        return " ".join(results)

    def _execute_text_task(
            self, method_name, response_attr, chunks, base_kwargs_builder, extra_kwargs=None,
    ):
        try:
            extra_kwargs = extra_kwargs or {}

            def worker(chunk):
                try:
                    base_kwargs = base_kwargs_builder(chunk)

                    def normalize_value(v):
                        if isinstance(v, str) and v.lower() in ("true", "false"):
                            return v.lower() == "true"
                        return v

                    kwargs = {
                        **base_kwargs,
                        **{
                            k: normalize_value(v)
                            for k, v in extra_kwargs.items()
                            if v is not None
                        },
                    }

                    method = getattr(self.client.text, method_name)
                    response = method(**kwargs)
                    logger.info(f"Response {response}")

                    return getattr(response, response_attr, chunk)

                except Exception:
                    logger.error(f"{method_name} error")
                    return chunk

            return self._process_in_parallel(chunks, worker)

        except Exception:
            logger.error(f"{method_name} failed")
            raise

    def transliterate(
            self, input_text, source_lang, target_lang, max_chars=990, voice_provider=None,
    ):
        chunks = self.split_text_into_chunks(input_text, max_chars)

        other = getattr(voice_provider, "other_params", {}) or {}

        def base_kwargs_builder(chunk):
            return {
                "input": chunk,
                "source_language_code": source_lang,
                "target_language_code": target_lang,
            }

        return {
            "status": 200,
            "content": self._execute_text_task(
                method_name="transliterate",
                response_attr="transliterated_text",
                chunks=chunks,
                base_kwargs_builder=base_kwargs_builder,
                extra_kwargs={
                    "numerals_format": other.get("numerals_format"),
                    "spoken_form": other.get("spoken_form"),
                    "spoken_form_numerals_language": other.get("spoken_form_numerals_language"),
                },
            ),
        }

    def translate(self, input_text, source_lang, target_lang, max_chars=990, voice_provider=None):
        chunks = self.split_text_into_chunks(input_text, max_chars)

        other = getattr(voice_provider, "other_params", {}) or {}
        gender = getattr(voice_provider, "gender", None)

        def base_kwargs_builder(chunk):
            return {
                "input": chunk,
                "source_language_code": source_lang,
                "target_language_code": target_lang,
                "speaker_gender": gender,
            }

        return {
            "status": 200,
            "content": self._execute_text_task(
                method_name="translate",
                response_attr="translated_text",
                chunks=chunks,
                base_kwargs_builder=base_kwargs_builder,
                extra_kwargs={
                    "model": other.get("model"),
                    "mode": other.get("mode"),
                    "output_script": other.get("output_script"),
                    "numerals_format": other.get("numerals_format"),
                },
            ),
        }
