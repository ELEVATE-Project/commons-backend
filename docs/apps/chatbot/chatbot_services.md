# Chatbot Core Services

## Overview

The chatbot core services coordinate essential functions like session management, message preparations, prompt building, and orchestration of chatbot workflows to provide responsive conversational experiences.

## Key Services in Detail

### BaseChatService

The BaseChatService handles shared operations essential for chatbot function:

- Manages database queries to fetch session-related data such as chat messages, user Profile, chat sessions, and bot configurations.
- Retrieves bot vernacular settings to produce personalized introductory messages including user first name injection.
- Extracts detailed user profile info, eg. location, for use in conversation customization and context.

### ChatOrchestrator

The ChatOrchestrator serves as the central controller managing overall chat processing:

- Utilizes BaseChatService to gather necessary session data.
- Prepares and filters messages to be used in responses.
- Delegates session processing to a designated bot strategy based on bot type.
- Constructs system prompts tailored for the language model provider in use.
- Handles chat response collection and logs output.
- Includes error handling mechanisms to ensure robust processing.

### MessageHandler

This service focuses on efficiently preparing chatbot messages:

- Prepares message sets combining chats and introductory prompts.
- Filters chats further using state machine configuration for precise message scope.

### PromptBuilder

Responsible for generating system prompt content:

- Builds concatenated prompts comprising bot context, state machine context, and completion criteria.
- Formats prompts differently based on large language model provider (Bedrock, OpenAI, etc.).

### BotServiceFactory

Employs factory pattern for creating bot strategy instances:

- Supports known bot strategies including 'oneshot', 'guided_guest', 'guest_discussion', and 'common'.
- Allows dynamic extension by registering additional bot strategy classes.

This service layer delivers the foundation enabling versatile chatbot operations supporting multiple interaction designs.

The core services in the chatbot app encapsulate essential functionalities required to manage chat sessions, prepare messages, build prompts, and orchestrate the chatbot's workflow.

These services are primarily located in `chatbot/services/core/`.

## BaseChatService

- Provides shared database operations like fetching session data, user profile, and bot vernacular.
- Methods:
  - `get_session_data(session_id, profile_id, bot_route)`: Fetches company chats, chat session, profile, and company bot.
  - `get_bot_vernacular_and_intro(company_bot, profile)`: Retrieves bot vernacular and generates introductory messages.
  - `get_user_profile_info(profile)`: Extracts user profile information like name and location.

## ChatOrchestrator

- Central orchestrator for chat processing.
- Interacts with services/core components and bot strategies.
- Main method: `process_chat_request(channel_name, session_id, profile_id, language)` handles the chat session processing flow including:
  - Fetching session data
  - Preparing messages
  - Processing session with strategy
  - Filtering messages
  - Building prompts
  - Getting responses from strategy
  - Handling errors

## MessageHandler

- Responsible for message preparation and filtering.
- Methods:
  - `prepare_messages(company_bot, company_chats, intro_mssg, other_info)`: Prepares and formats messages.
  - `get_filtered_chats(session_id, state_machine, company_chats)`: Fetches chats filtered by state machine if required.

## PromptBuilder

- Builds system prompts for use with large language model providers.
- Supports different LLM providers with tailored prompt formats.
- Method: `build_system_prompt(company_bot, state_machine)`

## BotServiceFactory

- Factory class to instantiate the appropriate bot strategy based on bot type.
- Maps bot types like 'oneshot', 'guided_guest', 'guest_discussion', and 'common' to their strategy classes.
- Methods:
  - `create_bot_service(bot_type, route=None, extra_params=None)`
  - `register_strategy(bot_type, strategy_class)` to add new strategies.
