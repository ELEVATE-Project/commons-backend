
from enum import Enum
from typing import Dict, List, Any
from chatbot.constants.post_processing_constants import PROCESSING_TYPE_CONFIG


# Common fields that all processing types share
COMMON_FIELDS = ['input_file', 'date_from', 'date_till']


class ProcessingType(Enum):
    """
    Enum for all available post-processing types.
    """
    UNIQUE_CHALLENGES = 'unique_challenges'
    UNIQUE_SOLUTIONS = 'unique_solutions'
    
    @property
    def label(self) -> str:
        """Human-readable label for the processing type"""
        return PROCESSING_TYPE_CONFIG[self.value]['label']
    
    @property
    def template_name(self) -> str:
        """Template file name for the processing type's form fields"""
        return PROCESSING_TYPE_CONFIG[self.value]['template_name']
    
    @property
    def fields(self) -> List[Dict[str, Any]]:
        """Configuration for form fields specific to this processing type"""
        return PROCESSING_TYPE_CONFIG[self.value]['fields']
    
    @property
    def handler_method(self) -> str:
        """Name of the method in PostProcessingView that handles this type"""
        return PROCESSING_TYPE_CONFIG[self.value]['handler_method']


def get_all_processing_types() -> List[Dict[str, str]]:
    return [
        {
            'value': ptype.value,
            'label': ptype.label
        }
        for ptype in ProcessingType
    ]


def get_processing_type_by_value(value: str) -> ProcessingType:
    for ptype in ProcessingType:
        if ptype.value == value:
            return ptype
    return None


def get_processing_type_config(processing_type: ProcessingType) -> Dict[str, Any]:
    """Get configuration dictionary for a specific processing type"""
    return PROCESSING_TYPE_CONFIG.get(processing_type.value, {})
