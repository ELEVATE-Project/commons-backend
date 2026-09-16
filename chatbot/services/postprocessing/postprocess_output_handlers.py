import json
from chatbot.models import PostProcessOutputMode
import json_repair
import logging

logger = logging.getLogger('django')


class PostprocessOutputHandler:
    """Handles different postprocessing output modes"""

    @staticmethod
    def handle_output(output_mode, postprocess_response, llm_response, **kwargs):
        """Handle postprocessing output based on mode"""
        if output_mode == PostProcessOutputMode.SKIP:
            return PostprocessSkipOutputHandler.handle(postprocess_response, llm_response, **kwargs)
        else:
            return {'action': 'continue', 'skip_next_stage': False}


class PostprocessSkipOutputHandler:
    """Handles SKIP output mode for postprocessing"""

    @staticmethod
    def handle(postprocess_response, llm_response, **kwargs):
        """
        Determine if we should skip the next stage based on postprocess response.
        :param postprocess_response: Raw string or dict-like response from LLM.
        :param llm_response: Original LLM raw response for fallback.
        :return: Dict with skip flag.
        """
        logger.info(f"[PostprocessSkipOutputHandler] Handling SKIP mode.")
        logger.info(f"[PostprocessSkipOutputHandler] postprocess_response type: {type(postprocess_response)}")
        logger.info(f"[PostprocessSkipOutputHandler] postprocess_response: {postprocess_response}")

        if not postprocess_response:
            logger.info("[PostprocessSkipOutputHandler] No postprocess_response provided. Continue to next stage.")
            return {'action': 'continue', 'skip_next_stage': False}

        should_skip = False

        parsed = None
        if isinstance(postprocess_response, dict):
            logger.info("[PostprocessSkipOutputHandler] postprocess_response is already a dict.")
            parsed = postprocess_response
        else:
            try:
                logger.info(f"[PostprocessSkipOutputHandler] Parsed JSON successfully: {parsed}")
                parsed = json_repair.repair_json(postprocess_response, return_objects=True)
            except json.JSONDecodeError:
                logger.error("[PostprocessSkipOutputHandler] Failed to parse JSON. Using fallback text mode.")
                parsed = None

        # If it's a dict, only check known keys
        if isinstance(parsed, dict):
            for key, val in parsed.items():
                logger.info(f"[PostprocessSkipOutputHandler] Checking key='{key}', value={val}")
                key_lower = str(key).lower()
                # Ignore reasoning-type fields
                if any(skip_word in key_lower for skip_word in ["reason", "reasoning", "explanation"]):
                    logger.info(f"[PostprocessSkipOutputHandler] Skipping check for key '{key}' (reasoning/explanation).")
                    continue

                if isinstance(val, bool):
                    logger.info(f"[PostprocessSkipOutputHandler] Boolean value detected: {val}")
                    if val:  # Only skip if true
                        logger.info(f"[PostprocessSkipOutputHandler] Skip triggered by boolean True in key '{key}'.")
                        should_skip = True
                        break
                elif isinstance(val, str):
                    val_stripped = val.strip().lower()
                    logger.info(f"[PostprocessSkipOutputHandler] String value detected: '{val_stripped}'")
                    if val_stripped in ["yes", "true", "skip"]:
                        should_skip = True
                        logger.info(f"[PostprocessSkipOutputHandler] Skip triggered by string '{val_stripped}' in key '{key}'.")
                        break

        # If not JSON, fallback to strict keyword match
        else:
            text = str(postprocess_response).strip().lower()
            logger.info(f"[PostprocessSkipOutputHandler] Fallback text mode. Processed text: '{text}'")
            # only match whole words to avoid "yes" inside sentences
            if text in ["skip", "yes", "true"]:
                should_skip = True
                logger.info(f"[PostprocessSkipOutputHandler] Skip triggered by fallback text '{text}'.")


        logger.info(f"[PostprocessSkipOutputHandler] Final decision: skip_next_stage={should_skip}")
        return {'action': 'continue', 'skip_next_stage': should_skip}