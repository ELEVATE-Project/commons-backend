# Ubiquitous Language

## Core Entities

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Company** | An organisation that owns one or more bots and whose users interact with them | Tenant, organisation, client |
| **CompanyBot** | A specific bot configuration (LLM model, prompts, strategy, timeouts) belonging to a Company | Bot config, chatbot instance |
| **Profile** | A user record tied to a Company; holds personal data and auth credentials | User, account, login |
| **CompanyChat** | A single chat message (turn) sent by a Profile or the bot within a Session | Message, chat turn, utterance |
| **ChatSession** | An active conversation thread between a Profile and a CompanyBot; tracks current step, language, and status | Session object, chat thread |
| **Story** | A structured narrative document produced at the end of a ChatSession, authored by a Profile | Report, output, reflection doc |
| **StoryTranslation** | A vernacular (non-English) translation of a Story's content | Vernacular story, translated story |
| **Flow** | A named conversation configuration that groups a CompanyBot, State Machines, Voice configs, and language settings into a deployable unit | Route config, conversation config |

## Conversation Structure

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **StateMachine** (CompanyStateMachine) | A single ordered step in a structured bot workflow; defines prompts, pre/post-process rules, and stage chats for that step | Wizard step, conversation node |
| **Step** | The integer position within a StateMachine sequence; determines which StateMachine is active in a ChatSession | Index, turn number |
| **ChatStage** | A named strand within a structured conversation (e.g. Welcome\_Strand, Courage\_Strand); used to scope which messages are passed to the LLM | Strand, phase |
| **BotStrategy** | The top-level conversation pattern used by a CompanyBot (oneshot, guided\_guest, guest\_discussion, common) | Mode, bot type |
| **ChatType** | The workflow variant of a session (e.g. Guided Reflection, One-Step Reflection, Mega PTM, PPS, Free Flow) | Flow type, session mode |
| **SessionFlow** | The named entry-point route that a user follows to start a session (e.g. guest-discussion, login, megaPTM, parent\_perception\_survey) | URL flow, route |

## PTM & Survey Domain

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **PTM** | Parent-Teacher Meeting; the real-world event this service captures data about | Parent meeting |
| **PTM Reflection** | A Story produced from a Mega PTM session capturing a participant's PTM experience | PTM report, PTM story |
| **PPS (Parent Perception Survey)** | A survey flow capturing parents' perceptions of school quality and change | Parent survey |
| **PTM Experience Summary** | Free-text narrative within a PTM Reflection summarising the participant's PTM experience | Summary, notes |
| **Key Highlights** | Structured notable points extracted from a PTM Reflection | Takeaways, highlights |
| **Perceived Changes / Impact** | Outcomes and improvements observed by the participant that are recorded in a PTM Reflection | Impact section |
| **Role** | The participant's relationship to the school (e.g. parent, teacher, headmaster) as captured in a PTM session | Designation (use designation only for Profile, not PTM context) |

## Translation & Voice

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Voice** | A configured speech provider entry (STT, TTS, or text translation) attached to a CompanyBot | Voice config, audio config |
| **VoiceType** | The operation a Voice performs: SpeechToText, TextToSpeech, TextToText (translation), or Transliterate | Voice mode |
| **VoiceProvider** | The external service that handles a VoiceType (AI4Bharat, Google, Sarvam, OpenAI Whisper) | Speech engine |
| **Vernacular** | Any supported Indian language other than English (Hindi, Kannada, Telugu, Odia) | Regional language, local language |

## Processing Pipeline

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **PreProcess** | An optional transformation applied to the prompt before the main LLM call; can modify or skip the current step | Pre-hook, prompt transform |
| **PostProcess** | An optional refinement applied to the LLM response after generation; can skip the next step | Post-hook, response transform |
| **DynamicContext** | Runtime-generated context injected into a prompt via SQL query or Python script | Dynamic prompt, live context |

## Knowledge Service

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Media** | An uploaded document (PDF, DOCX, Excel, CSV, image) attached to a CompanyBot for RAG or display | Document, file, attachment |
| **Tag** | A classification label applied to a Story or Media; can be manual or AI-extracted | Label, category |
| **Knowledge Service** | The subsystem that ingests Media, extracts text, and auto-tags content for LLM retrieval | Document service, RAG pipeline |

## Actors

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Guest** | An unauthenticated user who interacts via a guest flow without a verified Profile | Anonymous user, visitor |
| **Authenticated User** | A Profile with verified credentials who uses a login-gated flow | Logged-in user, auth user |
| **Moderator** | A Profile with elevated privileges for reviewing and managing content | Admin user, reviewer |

## Relationships

- A **Company** owns many **CompanyBots** and many **Profiles**.
- A **CompanyBot** is configured with one **BotStrategy** and one or more **StateMachines** (when `bot_type = STATE_MACHINE`).
- A **Flow** groups a **CompanyBot** with its **StateMachines**, **Voices**, and language settings into a deployable unit.
- A **ChatSession** is tied to one **Profile** and one **CompanyBot**; its `current_step` points to the active **StateMachine**.
- Each turn produces one **CompanyChat** record; multiple **CompanyChats** belong to one **ChatSession** via `session`.
- At the end of a PTM or reflection flow, one **Story** is created per **ChatSession**; a **Story** may have zero or more **StoryTranslations** for **Vernacular** languages.
- A **Tag** belongs to one **Story** or one **Media** record.

## Example dialogue

> **Dev:** "After the last step fires, do we create the Story immediately or wait?"
>
> **Domain expert:** "The Celery task `create_ptm_report` runs async. It calls `create_story_object`, which writes a **PTM Reflection** Story and, if the **ChatSession** language is vernacular, creates a **StoryTranslation** in that language."
>
> **Dev:** "So the Story's `stage` field — is that the same as the ChatSession's `current_step`?"
>
> **Domain expert:** "No. `stage` on Story is lifecycle: PENDING or COMPLETED. `current_step` on ChatSession is the integer index into the **StateMachine** sequence. Totally separate."
>
> **Dev:** "And the `flow` param passed into the task — is that a Flow model ID or a SessionFlowName string?"
>
> **Domain expert:** "It's a **SessionFlowName** string (e.g. `'megaPTM'`). It gets stored in `other_params` on the Story for downstream reporting. The actual **Flow** model is on the ChatSession."
>
> **Dev:** "Got it. One more: if a parent speaks Telugu, which component translates the bot's question before it's sent?"
>
> **Domain expert:** "The **Voice** record with `type = TextToText` and `language = 'te'` routes through the configured **VoiceProvider** (usually Sarvam or AI4Bharat). The translated text is stored as `translated_message` on **CompanyChat**."

## Flagged ambiguities

- **"session"** is overloaded: the `ChatSession` model object vs. the bare `session` CharField (a UUID string) used as the join key on `CompanyChat` and `Story`. Prefer **ChatSession** for the object and **session ID** for the string.
- **"stage"** means two different things: (1) `ChatStage` — a named conversation strand (Welcome\_Strand, Courage\_Strand) scoping which messages are sent to the LLM; (2) `Story.stage` — the lifecycle state (PENDING / COMPLETED). Always qualify: **ChatStage** vs. **Story stage**.
- **"flow"** appears as three distinct concepts: (1) the `Flow` model; (2) the `SessionFlowName` string enum; (3) the `ChatType` enum. Use **Flow** for the model, **SessionFlow** for the route/entry-point string, and **ChatType** for the workflow variant.
- **"status"** is used on `Company`/`Profile` (ACTIVE/INACTIVE entity status), `ChatSession` (STARTED/IN\_PROGRESS/COMPLETED/PAUSED), and `CompanyChat` (message-level status). Always prefix: **entity status**, **session status**, **message status**.
- **"role"** in PTM context (parent, teacher, headmaster) is distinct from **"profile\_type"** (USER, MODERATOR, PROSPECT) on the Profile model. Use **role** only for PTM participant context; use **profile type** for system access level.
