

class StoryError(Exception):
    """Base story exception"""
    code = "generic_error"


class StoryDomainError(StoryError):
    code = "domain_error"


class StoryValidationError(StoryError):
    code = "missing_fields"


class StorySaveError(StoryError):
    code = "generic_error"
