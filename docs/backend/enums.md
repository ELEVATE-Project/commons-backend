# Django Enums

`chatbot/models/enums.py`

This document defines all enumeration classes used across the platform.

Enums ensure consistency, validation, and type safety for status fields, providers, configuration types, and workflow definitions.

---

## 1. ChatStageChoices

### Purpose

Represents predefined conversational stages in structured chat flows.
    Used in state-machine based bots to control progression.

### Values

| Name | Value |
|------|-------|
| WELCOME | Welcome_Strand |
| ACHIEVEMENT_ORIENTATION | Achievement_Orientation |
| COURAGE | Courage_Strand |
| CONTINUOUS_LEARNING | Continuous_Strand |
| CRITICAL_THINKING | Critical_Thinking_Strand |
| PURPOSE | Purpose_Strand |
| THANKYOU | Thank_You_Strand |
| OTHER | Other |

---

## 2. ChatStatus

### Purpose

Represents the lifecycle status of a chat session.
    Used to track conversation progress and state transitions.

### Values

| Name | Value |
|------|-------|
| STARTED | STARTED |
| IN_PROGRESS | IN_PROGRESS |
| COMPLETED | COMPLETED |
| PAUSED | PAUSED |
| RESUME | RESUME |

---

## 3. ChatType

### Purpose

Defines supported chat workflow types.
    Controls conversation structure and bot behavior.

### Values

| Name | Value |
|------|-------|
| guidedReflection | normal |
| oneStepReflection | oneshot |
| shikshaChaupal | shikshalokam_chaupal |
| reflection | reflection |
| creation | creation |
| megaPTM | megaPTM |
| YLC | YLC |
| listeningActivity | listening-activity |
| ParentPerceptionSurvey | parent_perception_survey |
| LCF | lcf |
| LFA | lfa |
| FreeFlow | free_flow |

---

## 4. CompanyBotDynamicContextType

### Purpose

Specifies dynamic context generation mechanism.
    Supports SQL queries or Python scripts.

### Values

| Name | Value |
|------|-------|
| SQL_QUERY | SQL_QUERY |
| PYTHON_SCRIPT | PYTHON_SCRIPT |

---

## 5. CompanyBotTypeChoices

### Purpose

Defines architecture type of company bots.
    Determines conversation execution strategy.

### Values

| Name | Value |
|------|-------|
| SIMPLE | SIMPLE |
| STATE_MACHINE | STATE_MACHINE |
| DATABASE_SIMPLE | DATABASE_SIMPLE |
| INTERVIEW_STATE_MACHINE | INTERVIEW_STATE_MACHINE |

---

## 6. CompanyChatSourceChoices

### Purpose

Identifies source platform of a chat session.
    Used for analytics and usage tracking.

### Values

| Name | Value |
|------|-------|
| WEB | WEB |
| PHONE | PHONE |

---

## 7. EntityStatus

### Purpose

Indicates whether an entity is active or inactive.
    Supports soft-deletion and visibility control.

### Values

| Name | Value |
|------|-------|
| ACTIVE | ACTIVE |
| INACTIVE | INACTIVE |

---

## 8. EntityTypeChoices

### Purpose

Marks whether an entity is mandatory or optional.
    Used in dynamic validation and schema enforcement.

### Values

| Name | Value |
|------|-------|
| MANDATORY | MANDATORY |
| OPTIONAL | OPTIONAL |

---

## 9. FeedbackChoices

### Purpose

Captures feedback sentiment classification.
    Used for analytics and rating systems.

### Values

| Name | Value |
|------|-------|
| POSITIVE | POSITIVE |
| NEGATIVE | NEGATIVE |

---

## 10. FileDisplayMode

### Purpose

Controls file visibility scope and permissions.
    Determines access for UI and AI processing.

### Values

| Name | Value |
|------|-------|
| VISIBLE | visible |
| AI_ONLY | ai_only |
| PRIVATE | private |

---

## 11. FileTypeChoices

### Purpose

Supported document file types with utility helpers.
    Provides MIME, extension, and validation methods.

### Values

| Name | Value |
|------|-------|
| PDF | application/pdf |
| DOC | application/msword |
| DOCX | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| TXT | text/plain |
| CSV | text/csv |
| XLS | application/vnd.ms-excel |
| XLSX | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |

---

## 12. GenderChoices

### Purpose

Stores supported gender options.
    Used in user demographic information.

### Values

| Name | Value |
|------|-------|
| MALE | Male |
| FEMALE | Female |

---

## 13. LLMModel

### Purpose

Enumerates all supported AI model identifiers.
    Used for dynamic model configuration.

### Values

| Name | Value |
|------|-------|
| GPT4 | gpt-4 |
| GPT4_1 | gpt-4.1 |
| GPT4_1_MINI | gpt-4.1-mini |
| GPT4_128K | gpt-4-1106-preview |
| GPT4_TURBO | gpt-4-turbo |
| LLAMA_3_8B_8192 | llama3-8b-8192 |
| LLAMA_3_70B_8192 | llama3-70b-8192 |
| LLAMA_3_1_70B_VERSATILE | llama-3.1-70b-versatile |
| LLAMA_3_1_8B_INSTANT | llama-3.1-8b-instant |
| LLAMA_3_1_70B_INSTRUCT | meta.llama3-1-70b-instruct-v1:0 |
| LLAMA_3_1_8B_INSTRUCT | meta.llama3-1-8b-instruct-v1:0 |
| LLAMA_3_3_70B_INSTRUCT | us.meta.llama3-3-70b-instruct-v1:0 |
| LLAMA_3_3_8B_INSTRUCT | us.meta.llama3-3-8b-instruct-v1:0 |
| MIXTRAL_8X70B_32768 | mixtral-8x7b-32768 |
| GPT4_O | gpt-4o |
| GPT4_O_MINI | gpt-4o-mini |
| LLAMA_3_1_8B_OPS | meta-llama/Meta-Llama-3.1-8B-Instruct |
| GPT5_2 | gpt-5.2 |
| GPT5_2_PRO | gpt-5.2-pro |
| GPT5_MINI | gpt-5-mini |

---

## 14. LLMProvider

### Purpose

Lists supported Large Language Model providers.
    Determines which AI backend service is used.

### Values

| Name | Value |
|------|-------|
| BEDROCK | bedrock |
| BEDROCK_CONVERSE | bedrock/converse |
| OPENAI | openai |

---

## 15. LanguageChoices

### Purpose

Lists supported language-region codes.
    Used for localization and speech services.

### Values

| Name | Value |
|------|-------|
| INDIAN_ENGLISH | en-IN |
| INDIAN_HINDI | hi-IN |
| US_ENGLISH | en-US |
| INDIAN_KANNADA | kn-IN |

---

## 16. MediaTemplateChoices

### Purpose

Defines supported media template formats.
    Used in content rendering workflows.

### Values

| Name | Value |
|------|-------|
| EJS | EJS |
| RAW_TEXT | RAW-TEXT |

---

## 17. MediaTypeChoices

### Purpose

Supported MIME types for uploaded media.
    Used for validation and content handling.

### Values

| Name | Value |
|------|-------|
| PDF | application/pdf |
| TXT | text/plain |
| CSV | text/csv |
| JPEG | image/jpeg |
| PNG | image/png |
| SVG | image/svg+xml |
| WEBP | image/webp |
| HEIF | image/heif |
| HEIC | image/heic |
| XLSX | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |

---

## 18. PDFStrategyChoices

### Purpose

Lists available PDF generation strategies.
    Determines rendering engine implementation.

### Values

| Name | Value |
|------|-------|
| HTMLPDF | HTMLPDF |
| PUPPETEER | PUPPETEER |
| HTMLDOCX | HTMLDOCX |
| XLSX | XLSX |

---

## 19. PostProcessOutputMode

### Purpose

Controls workflow behavior after postprocessing.
    Can skip execution of the next stage.

### Values

| Name | Value |
|------|-------|
| NONE | NONE |
| SKIP | SKIP |

---

## 20. PostProcessType

### Purpose

Defines postprocessing strategy after LLM response.
    Used for response refinement and enhancement.

### Values

| Name | Value |
|------|-------|
| NONE | NONE |
| SIMPLE | SIMPLE |
| COMPLEX | COMPLEX |

---

## 21. PreProcessOutputMode

### Purpose

Controls behavior after preprocessing stage.
    Can skip execution of the current stage.

### Values

| Name | Value |
|------|-------|
| NONE | NONE |
| SKIP | SKIP |

---

## 22. PreProcessType

### Purpose

Defines preprocessing strategy before LLM execution.
    Controls prompt transformation complexity.

### Values

| Name | Value |
|------|-------|
| NONE | NONE |
| SIMPLE | SIMPLE |
| COMPLEX | COMPLEX |

---

## 23. ProfileType

### Purpose

Defines different user profile roles.
    Used for access control and permissions.

### Values

| Name | Value |
|------|-------|
| USER | USER |
| MODERATOR | MODERATOR |
| PROSPECT | PROSPECT |

---

## 24. RouteLanguageChoices

### Purpose

Maps URL route prefixes to language codes.
    Used for multilingual routing configuration.

### Values

| Name | Value |
|------|-------|
| ENGLISH | en |
| HINDI | hi |
| KANNADA | kn |
| TELUGU | te |

---

## 25. SessionFlowName

### Purpose

Represents predefined session flow identifiers.
    Used to control guest, login, and special flows.

### Values

| Name | Value |
|------|-------|
| GuestDiscussion | guest-discussion |
| LoginDiscussion | login-discussion |
| GuestMiStory | guest-mi-story |
| ListeningActivity | listening-activity |
| LoginMiStory | login |
| SsoFlow | sso |
| Reflection | reflection |
| megaPTM | megaPTM |
| YLC | YLC |
| ParentPerceptionSurvey | parent_perception_survey |
| creation | creation |

---

## 26. StoryLanguageChoices

### Purpose

Lists supported languages for stories.
    Used for multilingual story management.

### Values

| Name | Value |
|------|-------|
| ENGLISH | en |
| HINDI | hi |
| KANNADA | kn |
| TELUGU | te |

---

## 27. StorySourceChoices

### Purpose

Specifies origin of story content.
    Tracks AI, user, or third-party sources.

### Values

| Name | Value |
|------|-------|
| AI_GENERATED | AI_GENERATED |
| USER_GENERATED | USER_GENERATED |
| THIRD_PARTY | THIRD_PARTY |

---

## 28. StoryStatusChoices

### Purpose

Represents lifecycle state of a story.
    Used to track processing and completion status.

### Values

| Name | Value |
|------|-------|
| PENDING | PENDING |
| COMPLETED | COMPLETED |

---

## 29. TagChoices

### Purpose

Defines moderation status for tags.
    Used in approval and publishing workflows.

### Values

| Name | Value |
|------|-------|
| APPROVED | Approved |
| PENDING | Pending |

---

## 30. TagSourceChoices

### Purpose

Identifies origin of a tag entry.
    Distinguishes manual and AI-based tagging.

### Values

| Name | Value |
|------|-------|
| MANUAL | MANUAL |
| AI_EXTRACTED | AI_EXTRACTED |
| AI_GENERATED | AI_GENERATED |

---

## 31. TextConversionType

### Purpose

Specifies text transformation operation type.
    Supports translation and transliteration modes.

### Values

| Name | Value |
|------|-------|
| TRANSLATE | TRANSLATE |
| TRANSLITERATE | TRANSLITERATE |

---

## 32. ThemeType

### Purpose

Specifies theme source for a bot instance.
    Used to select custom or master UI themes.

### Values

| Name | Value |
|------|-------|
| CUSTOM | custom |
| MASTER | master |

---

## 33. VoiceProvider

### Purpose

Lists supported speech processing providers.
    Used for transcription and voice synthesis services.

### Values

| Name | Value |
|------|-------|
| GOOGLE | GOOGLE |
| GOOGLE_V1 | GOOGLE_V1 |
| AI4Bharat | AI4Bharat |
| OPENAI_WHISPER | OPENAI_WHISPER |
| SARVAM | Sarvam |

---

## 34. VoiceProviderChoices

### Purpose

Lists supported cloud voice providers.
    Used for speech-to-text and text-to-speech services.

### Values

| Name | Value |
|------|-------|
| AWS | aws |
| GCP | gcp |
| AZURE | azure |
| ELEVEN_LABS | eleven-labs |

---

## 35. VoiceType

### Purpose

Defines type of voice processing operation.
    Covers STT, TTS, and transliteration modes.

### Values

| Name | Value |
|------|-------|
| SpeechToText | SpeechToText |
| TextToText | TextToText |
| TextToSpeech | TextToSpeech |
| Transliterate | Transliterate |

---
