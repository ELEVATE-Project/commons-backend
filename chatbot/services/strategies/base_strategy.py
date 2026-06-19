from abc import ABC, abstractmethod
from chatbot.models.company_models import CompanyStateMachine


class BotStrategy(ABC):
    """Abstract base class for different bot strategies"""

    def __init__(self, route=None, extra_params=None):
        self.route = route or self.get_default_route()
        self.extra_params = extra_params if extra_params else {}
        from ..response_handlers.handler_factory import ResponseHandlerFactory
        self.response_handler = ResponseHandlerFactory.create_handler(handler_type=self.get_handler_type())

    @abstractmethod
    def get_default_route(self):
        """Get the default route for this strategy"""
        pass

    def get_route(self):
        return self.route

    @abstractmethod
    def get_handler_type(self):
        """Get the handler type for this strategy"""
        pass

    @abstractmethod
    def process_session(self, session_data, **kwargs):
        pass

    @abstractmethod
    def get_response(self, **kwargs):
        pass
