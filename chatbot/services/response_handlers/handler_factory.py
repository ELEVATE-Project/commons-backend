from chatbot.services.response_handlers.common_handler import CommonResponseHandler
from chatbot.services.response_handlers.discussion_guest_handler import GuestDiscussionResponseHandler
from chatbot.services.response_handlers.guided_guest_handler import GuidedGuestResponseHandler
from chatbot.services.response_handlers.oneshot_handler import OneShotResponseHandler


class ResponseHandlerFactory:
    """Factory for creating response handlers"""

    _handlers = {
        'guided_guest': GuidedGuestResponseHandler,
        'oneshot': OneShotResponseHandler,
        'guest_discussion': GuestDiscussionResponseHandler,
        'common': CommonResponseHandler,
    }

    @classmethod
    def create_handler(cls, handler_type):
        """Create response handler by type"""
        handler_class = cls._handlers.get(handler_type)
        if not handler_class:
            raise ValueError(f"Unknown handler type: {handler_type}")
        return handler_class()

    @classmethod
    def register_handler(cls, handler_type, handler_class):
        """Register new response handler"""
        cls._handlers[handler_type] = handler_class
