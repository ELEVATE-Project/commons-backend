# Chatbot Celery Tasks

## Overview

Celery tasks support asynchronous execution of chatbot workloads allowing responsive UX and offloading heavy operations.

## Key Celery Task Modules

### handle_message.py

- Utility methods for sending and translating messages on websocket channels.
- Utilizes Django Channels for WebSocket integration.

### chaupal_tasks.py

- Implements tasks for managing Chaupal style guest discussions, including flow control and session updates.

### common_chat_tasks.py

- Contains common chatbot task logic such as saving chat messages to DB.

### flow_tasks.py

- Manages chatbot flow processing tasks.

### free_flow_tasks.py

- Handles free form chatbot interactions asynchronously.

### guided_guest_tasks.py

- Supports guided guest chat flow tasks.

### mitra_bedrock_tasks.py, one_shot_bedrock_tasks.py, reflection_bedrock_tasks.py, shikshalokam_bedrock_tasks.py

- Integrate with Bedrock LLM services for various bot requirements.

### oneshot_guest_tasks.py

- Dedicated handling for one shot guest chatbot conversations.

### post_processing_tasks.py

- Handles operations executed after primary task completion.

### ptm_report_tasks.py

- Specific to PTM reporting workflows.

## Interaction

- Celery tasks are invoked primarily by websocket consumers and service layers.
- They ensure non-blocking operations and scalability.

---
