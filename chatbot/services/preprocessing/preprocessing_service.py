from chatbot.models import PreProcessType
from chatbot.services.preprocessing.base_preprocessor import SimplePreprocessor, ComplexPreprocessor
from chatbot.services.preprocessing.output_handlers import PreprocessOutputHandler
import logging

logger = logging.getLogger('django')


class PreprocessingService:
    """Main service for handling preprocessing operations"""

    def __init__(self):
        self.preprocessors = {
            PreProcessType.SIMPLE: SimplePreprocessor(),
            PreProcessType.COMPLEX: ComplexPreprocessor()
        }

    def execute_preprocessing(self, state_machine, original_prompt, **kwargs):
        """Execute preprocessing based on state machine configuration"""
        # Skip preprocessing if not configured
        if state_machine.preprocess_type == PreProcessType.NONE:
            return {'action': 'continue', 'prompt': original_prompt}

        # Get appropriate preprocessor
        preprocessor = self.preprocessors.get(state_machine.preprocess_type)
        if not preprocessor:
            logger.info(f"No preprocessor found for type: {state_machine.preprocess_type}")
            return {'action': 'continue', 'prompt': original_prompt}

        # Execute preprocessing
        logger.info(f"Executing {state_machine.preprocess_type} preprocessing for state: {state_machine.name}")
        preprocess_response = preprocessor.preprocess(state_machine, **kwargs)

        # Handle output based on mode
        result = PreprocessOutputHandler.handle_output(
            state_machine.preprocess_output_mode, preprocess_response, original_prompt, **kwargs
        )

        return result

    def register_preprocessor(self, preprocess_type, preprocessor):
        """Register a new preprocessor"""
        self.preprocessors[preprocess_type] = preprocessor
