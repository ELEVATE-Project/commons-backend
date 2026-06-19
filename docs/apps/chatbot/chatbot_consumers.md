# Chatbot WebSocket Consumers

## Overview

The `consumers` module manages real-time WebSocket connections for the chatbot, enabling continuous interactive chat experiences. It handles message receipt, session management, and asynchronous processing initiation.

## Primary Consumer

### AsyncSocketConsumer

- Located in `chatbot/consumers/async_consumer.py`.
- Extends `AsyncBaseConsumer` to implement core WebSocket lifecycle methods: connect, disconnect, and receive.
- Key features include:
  - Session and profile initialization on authentication messages.
  - Background task management using Celery for handling chat flow responses.
  - Message translation capabilities based on user-selected languages.
  - Asynchronous database operations for session creation and message logging.

## Other Consumer Modules

The `consumers` directory includes specialized consumers targeting different chatbot flows and LLM providers:

- **async_chaupal_consumer.py**: Handles Chaupal style guest discussion bots with long-running conversational contexts.
- **async_base_consumer.py**: Base class providing common WebSocket async consumer utilities.
- **base_consumer.py**: Synchronous base consumer class.
- **chaupal_consumer.py**: Synchronous consumer for Chaupal bots.
- **free_flow_consumer.py**: Handles free-form chatbot conversations.
- **guided_guest_consumer.py**: Manages guided guest chatbot interactions.
- **mitra_bedrock_consumer.py**, **one_shot_bedrock_consumer.py**, **shikshalokam_bedrock_consumer.py**: Integrations with Bedrock LLM provider for different bot types.
- **oneshot_guest_consumer.py**: One-shot guest chatbot conversation handling.
- **Reflection_bedrock_consumer.py**: Reflection bot using Bedrock.

Each specialized consumer adapts websocket interactions tailored for the specific chatbot flow or LLM provider use case.
