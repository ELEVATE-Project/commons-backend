# Backward compatibility - re-export models from their new locations
# This allows existing code to continue importing from base_models without breaking
from chatbot.models.company_models import (
    Company, CompanyBot, CompanyChat, Voice, CompanyStateMachine,
    ImageConfiguration, Flow
)
from chatbot.models.profile_models import Profile

__all__ = [
    'Company', 'CompanyBot', 'CompanyChat', 'Voice', 'CompanyStateMachine',
    'ImageConfiguration', 'Flow', 'Profile'
]
