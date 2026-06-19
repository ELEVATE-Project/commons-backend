from chatbot.models.enums import VoiceProvider, VoiceType


VOICE_PROVIDER_DEFAULTS = {
    VoiceProvider.AI4Bharat: {
        VoiceType.SpeechToText: {
            "chunk_duration": 10,
            "serviceId": "bhashini/iitm/asr-dravidian--gpu--t4",
            "samplingRate": 16000,
            "preProcessors": [],
            "postProcessors": []
        },
        VoiceType.TextToText: {
            "serviceId": "bhashini/iiith/nmt-all"
        },
        VoiceType.Transliterate: {},
        VoiceType.TextToSpeech: {
            "serviceId": "Bhashini/IITM/TTS",
            "samplingRate": 22050
        }
    },

    VoiceProvider.GOOGLE: {
        VoiceType.SpeechToText: {
            "chunk_duration": 10,
            "model": "latest_long",
            "location":"global",
            "enable_automatic_punctuation": False,
            "enable_spoken_punctuation": False,
            "enable_spoken_emojis": False,
            "max_alternatives": 1,
            "profanity_filter": False,
            "enable_word_time_offsets": False,
            "boost_words": []
        },
        VoiceType.TextToText: {
            "glossary_id": None,
            "location": "global"
        }
    },

    VoiceProvider.OPENAI_WHISPER: {
        VoiceType.SpeechToText: {
            "model": "whisper-1",
            "response_format": "text",
            "temperature": 0,
            "dictionary": [],
            "chunk_duration": 100
        }
    },

    VoiceProvider.SARVAM: {
        VoiceType.SpeechToText: {
            "chunk_duration": 10,
            "model": "saaras:v3",
            "mode": "transcribe",
        },
        VoiceType.TextToText: {
            "model": "mayura:v1",
            "mode": "modern-colloquial",
            "output_script": "fully-native",
            "numerals_format": "native"
        },
        VoiceType.TextToSpeech: {
            "model": "bulbul:v3",
            "speaker": "shubh",
            "speech_sample_rate": 24000,
            "output_audio_codec": "wav",
            "pace": 1.0,
            "temperature": 0.6
        },

        VoiceType.Transliterate: {
            "numerals_format": "native",
            "spoken_form": True,
            "spoken_form_numerals_language": "native"
        }
    },

    VoiceProvider.CUSTOM_LLM: {
        VoiceType.SpeechToText: {},
        VoiceType.TextToText: {
            "route": "/transliterate_text"
        },
        VoiceType.Transliterate: {
            "route": "/transliterate_text"
        },
    }
}


def get_provider_defaults(provider, voice_type):
    provider_defaults = VOICE_PROVIDER_DEFAULTS.get(provider, {})
    return provider_defaults.get(voice_type, {})
