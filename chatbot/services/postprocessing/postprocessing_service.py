from chatbot.models import PostProcessType
from chatbot.services.postprocessing.base_postprocessor import SimplePostprocessor, ComplexPostprocessor
from chatbot.services.postprocessing.postprocess_output_handlers import PostprocessOutputHandler
import logging

logger = logging.getLogger('django')


class PostprocessingService:
    """Main service for handling postprocessing operations"""

    def __init__(self):
        self.postprocessors = {
            PostProcessType.SIMPLE: SimplePostprocessor(),
            PostProcessType.COMPLEX: ComplexPostprocessor()
        }

    def execute_postprocessing(self, state_machine, llm_response, **kwargs):
        """Execute postprocessing based on state machine configuration"""
        # Skip postprocessing if not configured
        if state_machine.postprocess_type == PostProcessType.NONE:
            return {'action': 'continue', 'skip_next_stage': False}

        # Get appropriate postprocessor
        postprocessor = self.postprocessors.get(state_machine.postprocess_type)
        if not postprocessor:
            logger.warning(f"No postprocessor found for type: {state_machine.postprocess_type}")
            return {'action': 'continue', 'skip_next_stage': False}

        # Execute postprocessing
        logger.info(f"Executing {state_machine.postprocess_type} postprocessing for state: {state_machine.name}")
        postprocess_response = postprocessor.postprocess(state_machine, llm_response, **kwargs)

        # Handle output based on mode
        result = PostprocessOutputHandler.handle_output(
            state_machine.postprocess_output_mode,
            postprocess_response,
            llm_response,
            **kwargs
        )

        return result

    def register_postprocessor(self, postprocess_type, postprocessor):
        """Register a new postprocessor"""
        self.postprocessors[postprocess_type] = postprocessor
