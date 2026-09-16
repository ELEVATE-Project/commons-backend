# Bot Strategies

## Overview

The chatbot employs multiple bot strategies, each implementing distinct conversational flows tailored for specific use cases. All strategies inherit from the abstract `BotStrategy` base class located in `services/strategies/base_strategy.py`.

## Strategies Implemented

### CommonBotStrategy (Primary Strategy)

The CommonBotStrategy serves as the foundational strategy and is the default for any chatbot flow that does not require specialized behavior or customization. It is the backbone for all generic and future chatbot conversations.

- Uses the "common" response handler type.
- Processes the session by retrieving the current state machine step associated with the chat session.
- Offers extensibility to support a wide range of chatbot flows without the need for separate custom strategies.

### GuestDiscussionBotStrategy

This strategy is developed specifically for guest discussion or chaupal style bots.

- Default route set to `/shikshalokam_chaupal`.
- Processes the session using the relevant state machine tied to the current chat step.

### GuidedGuestBotStrategy

Tailored for guided guest chatbot interactions.

- Default route is `/guided_guest`.
- Similar session processing via state machine retrieval.
- Includes placeholders for potential future enhancement like step increments for new users.

### OneShotBotStrategy

Designed for one-shot conversation flows that follow pre-defined stages.

- Default route is `/oneshot_guest`.
- Determines the remaining stages in the conversation through utility methods.
- Updates the chat session's current step according to the state machine.
- Implements stage filtering based on user profile data.

This structured approach to bot strategies allows the chatbot to maintain a modular, extensible architecture supporting multiple conversational patterns while sharing a unified interface.
