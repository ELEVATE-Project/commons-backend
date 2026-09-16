# Observability Utilities

## Overview

This module includes utility functions that support the operations of the Observability app by providing helper methods for chat processing and deep evaluation model integration.

## preparechats.py

### get_chat_dict function

- Converts a chat session's messages into a dictionary format compatible with LLM input.
- Takes `chat_session_id` and an optional `exclude_end_ai_message` flag to omit the final AI message.
- Extracts messages ordered by creation time, differentiates by sender (user or assistant).
- Returns a list of dictionaries with roles (`user` or `assistant`) and message content.

## deepeval.py

### DeepEvalBaseLLM class

- Wraps the integration with the LiteLLM powered DeepEval base model.
- Supports synchronous (`generate`) and asynchronous (`a_generate`) message completions.
- Handles exceptions and returns model responses conforming to pydantic BaseModel expectations.
- Provides method to get a descriptive model name.
- Utilizes the `instructor` library for interfacing with the LiteLLM completion API.

---

These utilities are key enablers for preparing chat input for evaluation and executing those evaluation queries against specialized LLMs within the Observability app's testing framework.
