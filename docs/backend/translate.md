# Translation Integrations

The Translation layer integrates multiple external language providers and exposes a unified processing interface for:

- Speech-to-Text (STT)
- Text-to-Speech (TTS)
- Text Translation (T2T)
- Transliteration
- Language Detection

Each provider implementation resides under:

```
chatbot/translate/
```

All provider implementations return a standardized response:

```
{
    "status": int,
    "content": string
}
```

---

## 1. AI4Bharat (Bhashini / ULCA)

Implements multilingual processing using ULCA pipeline APIs.

Supports:

- Speech-to-Text
- Text-to-Speech
- Text Translation
- Transliteration
- Language Detection

---

### Service Resolution

`chatbot/translate/ai4Bharat/base_translation.py`

#### Purpose

Handles ULCA model discovery and dynamic service resolution.

#### Responsibilities

- Fetch available ULCA models
- Resolve `serviceId` based on:
  - taskType
  - sourceLanguage
  - targetLanguage
- Extract inference API keys
- Provide fallback service mappings

---

### Speech-to-Text (STT)

`chatbot/translate/ai4Bharat/speech_to_text.py`

#### Purpose

Implements Speech-to-Text using ULCA `asr` pipeline.

#### Responsibilities

- Accept base64 audio input
- Split large audio into chunks
- Process chunks in parallel
- Merge transcripts in correct order
- Handle sampling rate and audio format configuration

#### Input

```
{
    "base64_audio": string,
    "audio_format": string,
    "source_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "transcribed_text"
}
```

---

### Text-to-Speech (TTS)

`chatbot/translate/ai4Bharat/text_to_speech.py`

#### Purpose

Implements Text-to-Speech using ULCA `tts` pipeline.

#### Responsibilities

- Accept text input
- Configure gender
- Configure sampling rate
- Generate base64 encoded audio

#### Input

```
{
    "text": string,
    "source_language": string,
    "gender": string
}
```

#### Output

```
{
    "status": 200,
    "content": "base64_audio"
}
```

---

### Text Translation (T2T)

`chatbot/translate/ai4Bharat/text_to_text.py`

#### Purpose

Implements language-to-language translation.

#### Responsibilities

- Accept source and target languages
- Execute ULCA `translation` task
- Extract translated output

#### Input

```
{
    "text": string,
    "source_language": string,
    "target_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "translated_text"
}
```

---

### Transliteration

`chatbot/translate/ai4Bharat/transliterate.py`

#### Purpose

Implements script-level transliteration.

#### Responsibilities

- Resolve transliteration serviceId
- Convert between scripts
- Support sentence-level transliteration

#### Input

```
{
    "text": string,
    "source_language": string,
    "target_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "transliterated_text"
}
```

---

### Language Detection

`chatbot/translate/ai4Bharat/text_lang_detect.py`

#### Purpose

Detects language of input text.

#### Responsibilities

- Execute ULCA `txt-lang-detection`
- Extract ISO language code

#### Input

```
{
    "text": string
}
```

#### Output

```
{
    "status": 200,
    "content": "language_code"
}
```

---

## 2. Google Cloud

Implements language services using official Google Cloud SDK clients.

Supports:

- Speech-to-Text (v1 & v2)
- Text Translation
- Text-to-Speech

---

### Speech-to-Text (STT) – v1

`chatbot/translate/google/google_stt_v1.py`

#### Purpose

Performs long-running speech recognition using Speech v1 API.

#### Responsibilities

- Decode base64 audio
- Support multiple language codes
- Aggregate recognition results

#### Input

```
{
    "base64_audio": string,
    "language_codes": [string]
}
```

#### Output

```
{
    "status": 200,
    "content": "transcribed_text"
}
```

---

### Speech-to-Text (STT) – v2

`chatbot/translate/google/google_stt.py`

#### Purpose

Performs chunked speech recognition using Speech v2 API.

#### Responsibilities

- Split audio into chunks
- Parallel chunk transcription
- Use `latest_long` recognition model
- Merge transcripts in order

#### Input

```
{
    "project_id": string,
    "base64_audio": string,
    "language_codes": [string]
}
```

#### Output

```
{
    "status": 200,
    "content": "transcribed_text"
}
```

---

### Text Translation (T2T)

`chatbot/translate/google/google_translate.py`

#### Purpose

Performs text translation using Google Translation API.

#### Responsibilities

- Authenticate via service account
- Translate text between languages
- Return translated text

#### Input

```
{
    "text": string,
    "project_id": string,
    "source_language": string,
    "target_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "translated_text"
}
```

---

### Text-to-Speech (TTS)

`chatbot/translate/google/google_tts.py`

#### Purpose

Performs text-to-speech synthesis.

#### Responsibilities

- Accept text input
- Configure voice name
- Configure gender
- Configure speaking rate
- Generate MP3 audio

#### Input

```
{
    "text": string,
    "language_code": string
}
```

#### Output

```
{
    "status": 200,
    "content": "base64_audio"
}
```

---

## 3. OpenAI

Currently supports Whisper-based speech recognition.

---

### Speech-to-Text (STT)

`chatbot/translate/openai/openai_stt.py`

#### Purpose

Performs speech-to-text using OpenAI Whisper.

#### Responsibilities

- Decode base64 audio
- Convert to in-memory file
- Call Whisper model (`whisper-1`)
- Return transcription text

#### Input

```
{
    "base64_audio": string,
    "audio_format": string,
    "source_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "transcribed_text"
}
```

---

## 4. Sarvam AI

Implements speech and translation using SarvamAI SDK.

Supports:

- Speech-to-Text
- Text Translation

---

### Speech-to-Text (STT)

`chatbot/translate/sarvam/speech_to_text.py`

#### Purpose

Performs chunked speech recognition using SarvamAI.

#### Responsibilities

- Decode base64 audio
- Split audio into chunks
- Parallel chunk transcription
- Use `saarika:v2` model
- Merge transcripts

#### Input

```
{
    "base64_audio": string,
    "source_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "transcribed_text"
}
```

---

### Text Translation (T2T)

`chatbot/translate/sarvam/translate.py`

#### Purpose

Performs parallel chunked text translation.

#### Responsibilities

- Split long text safely
- Translate chunks in parallel
- Support:
  - mode
  - output_script
  - preprocessing
- Reassemble final output

#### Input

```
{
    "text": string,
    "source_language": string,
    "target_language": string
}
```

#### Output

```
{
    "status": 200,
    "content": "translated_text"
}
```

---

## 5. Shared Audio Utilities

### Audio Utilities

`chatbot/translate/base/speech_to_text.py`

#### Purpose

Provides reusable audio utilities used across providers.

#### Responsibilities

- Detect silent audio chunks
- Split audio into fixed-duration segments
- Ensure consistent chunking logic across
    - AI4Bharat
    - Google
    - Sarvam


