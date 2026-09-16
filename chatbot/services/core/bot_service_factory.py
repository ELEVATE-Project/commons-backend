from chatbot.services.strategies.common_strategy import CommonBotStrategy
from chatbot.services.strategies.guest_discussion import GuestDiscussionBotStrategy
from chatbot.services.strategies.guided import GuidedGuestBotStrategy
from chatbot.services.strategies.oneshot import OneShotBotStrategy


class BotServiceFactory:
    """Factory to create appropriate bot strategy"""

    _strategies = {
        'oneshot': OneShotBotStrategy,
        'guided_guest': GuidedGuestBotStrategy,
        'guest_discussion': GuestDiscussionBotStrategy,
        'common': CommonBotStrategy
    }

    @classmethod
    def create_bot_service(cls, bot_type, route=None, extra_params=None, **kwargs):
        """Create bot service based on type and optional route"""
        strategy_class = cls._strategies.get(bot_type)
        if not strategy_class:
            raise ValueError(f"Unknown bot type: {bot_type}")
        return strategy_class(route=route, extra_params=extra_params, **kwargs)

    @classmethod
    def register_strategy(cls, bot_type, strategy_class):
        """Register new bot strategy"""
        cls._strategies[bot_type] = strategy_class
