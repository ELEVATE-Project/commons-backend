import json
import json_repair
from chatbot.models import PreProcessOutputMode, LLMProvider
import logging

logger = logging.getLogger('django')


class PreprocessOutputHandler:
    """Handles different preprocessing output modes"""

    @staticmethod
    def handle_output(output_mode, preprocess_response, original_prompt, **kwargs):
        """Handle preprocessing output based on mode"""
        if output_mode == PreProcessOutputMode.SKIP:
            return SkipOutputHandler.handle(preprocess_response, **kwargs)
        elif output_mode == PreProcessOutputMode.MODIFY_QUESTION:
            return ModifyQuestionOutputHandler.handle(
                preprocess_response, original_prompt, **kwargs
            )
        else:
            return {'action': 'continue', 'prompt': original_prompt}


class SkipOutputHandler:
    """Handles SKIP output mode"""

    @staticmethod
    def handle(preprocess_response, **kwargs):
        """
        Determine if we should skip the next stage based on preprocess response.
        :param preprocess_response: Raw string or dict-like response from LLM.
        :return: Dict with skip flag.
        """
        logger.info(f"[SkipOutputHandler] Handling SKIP mode.")
        logger.info(f"[SkipOutputHandler] preprocess_response type: {type(preprocess_response)}")
        logger.info(f"[SkipOutputHandler] preprocess_response: {preprocess_response}")

        if not preprocess_response:
            logger.info("[SkipOutputHandler] No preprocess_response provided. Continue to next stage.")
            return {'action': 'continue'}

        should_skip = False

        if isinstance(preprocess_response, dict):
            logger.info("[SkipOutputHandler] preprocess_response is already a dict.")
            parsed = preprocess_response
        else:
            try:
                parsed = json_repair.repair_json(preprocess_response, return_objects=True)
                logger.info(f"[SkipOutputHandler] Parsed JSON successfully: {parsed}")
            except json.JSONDecodeError:
                logger.error("[SkipOutputHandler] Failed to parse JSON. Using fallback text mode.")
                parsed = None

        if isinstance(parsed, dict):
            for key, val in parsed.items():
                logger.info(f"[SkipOutputHandler] Checking key='{key}', value={val}")
                key_lower = str(key).lower()
                if any(skip_word in key_lower for skip_word in ["reason", "reasoning", "explanation"]):
                    logger.info(f"[SkipOutputHandler] Skipping check for key '{key}' (reasoning/explanation).")
                    continue

                if isinstance(val, bool):
                    logger.info(f"[SkipOutputHandler] Boolean value detected: {val}")
                    if val:
                        logger.info(f"[SkipOutputHandler] Skip triggered by boolean True in key '{key}'.")
                        should_skip = True
                        break
                elif isinstance(val, str):
                    val_stripped = val.strip().lower()
                    logger.info(f"[SkipOutputHandler] String value detected: '{val_stripped}'")
                    if val_stripped in ["yes", "true", "skip"]:
                        should_skip = True
                        logger.info(f"[SkipOutputHandler] Skip triggered by string '{val_stripped}' in key '{key}'.")
                        break

        else:
            text = str(preprocess_response).strip().lower()
            logger.info(f"[SkipOutputHandler] Fallback text mode. Processed text: '{text}'")
            if text in ["skip", "yes", "true"]:
                should_skip = True
                logger.info(f"[SkipOutputHandler] Skip triggered by fallback text '{text}'.")

        logger.info(f"[SkipOutputHandler] Final decision: skip={should_skip}")

        if should_skip:
            return {'action': 'skip'}
        else:
            return {'action': 'continue'}


class ModifyQuestionOutputHandler:
    """Handles MODIFY_QUESTION output mode"""

    @staticmethod
    def handle(preprocess_response, original_prompt, **kwargs):
        """
        Extract modified_question from preprocessing response.
        Falls back to original bot_question if parsing fails.
        """
        logger.info(f"[ModifyQuestionOutputHandler] Processing response")

        if not preprocess_response:
            logger.info("No preprocessing response, cannot modify question")
            return {'action': 'continue', 'prompt': original_prompt}

        modified_question = None

        if isinstance(preprocess_response, dict):
            parsed = preprocess_response
        else:
            try:
                parsed = json_repair.repair_json(preprocess_response, return_objects=True)
            except Exception as e:
                logger.error(f"Failed to parse preprocessing response: {e}")
                return {'action': 'continue', 'prompt': original_prompt}

        if isinstance(parsed, dict):
            modified_question = parsed.get('modified_question', '').strip()

        if modified_question:
            logger.info(f"Successfully extracted modified question: {modified_question[:100]}")
            return {
                'action': 'modify_question',
                'modified_bot_question': modified_question,
                'prompt': original_prompt
            }
        else:
            logger.info("No valid modified_question found, will use original")
            return {'action': 'continue', 'prompt': original_prompt}


class CustomOutputHandler:
    """Handles CUSTOM output mode"""

    @staticmethod
    def handle(preprocess_response, **kwargs):
        """Handle custom preprocessing logic"""
        logger.info(f"Custom preprocessing logic called with response: {preprocess_response}")
        print(f"CUSTOM PREPROCESSING: {preprocess_response}")

        # For now, just print and continue with original flow
        # In the future, this can be extended to call specific custom functions
        return {'action': 'continue'}
