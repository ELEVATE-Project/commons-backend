from random import choices

from django.db import models
from django.utils.translation import gettext_lazy as _


class ChatStatus(models.TextChoices):
    """
    Represents the lifecycle status of a chat session.
    Used to track conversation progress and state transitions.
    """
    STARTED = 'STARTED', _('STARTED')
    IN_PROGRESS = 'IN_PROGRESS', _('IN_PROGRESS')
    COMPLETED = 'COMPLETED', _('COMPLETED')
    PAUSED = 'PAUSED', _('PAUSED')
    RESUME = 'RESUME', _('RESUME')


class ChatType(models.TextChoices):
    """
    Defines supported chat workflow types.
    Controls conversation structure and bot behavior.
    """
    guidedReflection = 'normal', _('Guided Reflection')
    oneStepReflection = 'oneshot', _('One Step Reflection')
    shikshaChaupal = 'shikshalokam_chaupal', _('Shiksha Chaupal')
    reflection = 'reflection', _('Reflection')
    creation = 'creation', _('Creation')
    megaPTM = 'megaPTM', _('Mega PTM')
    YLC = 'YLC', _('YLC')
    listeningActivity = 'listening-activity', _('Listening Activity')
    ParentPerceptionSurvey = 'parent_perception_survey', _('Parent Perception Survey')
    LCF = 'lcf', _('LCF')
    LFA = 'lfa', _('LFA')
    FreeFlow = 'free_flow', _('Free-Flow')


class LLMProvider(models.TextChoices):
    """
    Lists supported Large Language Model providers.
    Determines which AI backend service is used.
    """
    BEDROCK = 'bedrock', _('BEDROCK')
    BEDROCK_CONVERSE = 'bedrock/converse', _('BEDROCK_CONVERSE')
    OPENAI = 'openai', _('OPENAI')


class ThemeType(models.TextChoices):
    """
    Specifies theme source for a bot instance.
    Used to select custom or master UI themes.
    """
    CUSTOM = 'custom', _('Custom for Bot')
    MASTER = 'master', _('Using Master Theme')


class LLMModel(models.TextChoices):
    """
    Enumerates all supported AI model identifiers.
    Used for dynamic model configuration.
    """
    GPT4 = 'gpt-4', _('GPT4')
    GPT4_1 = 'gpt-4.1', _('GPT4_1')
    GPT4_1_MINI = 'gpt-4.1-mini', _('GPT4_1-MINI')
    GPT4_128K = 'gpt-4-1106-preview', _('GPT4-128k')
    GPT4_TURBO = 'gpt-4-turbo', _('GPT4_TURBO')
    LLAMA_3_8B_8192 = 'llama3-8b-8192', _('LLAMA_3_8B_8192')
    LLAMA_3_70B_8192 = 'llama3-70b-8192', _('LLAMA_3_70B_8192')
    LLAMA_3_1_70B_VERSATILE = 'llama-3.1-70b-versatile', _('LLAMA_3_1_70B_VERSATILE')
    LLAMA_3_1_8B_INSTANT = 'llama-3.1-8b-instant', _('LLAMA_3_1_8B_INSTANT')
    LLAMA_3_1_70B_INSTRUCT = 'meta.llama3-1-70b-instruct-v1:0', _('LLAMA_3_1_70B_INSTRUCT')
    LLAMA_3_1_8B_INSTRUCT = 'meta.llama3-1-8b-instruct-v1:0', _('LLAMA_3_1_8B_INSTRUCT')
    LLAMA_3_3_70B_INSTRUCT = 'us.meta.llama3-3-70b-instruct-v1:0', _('LLAMA_3_3_70B_INSTRUCT')
    LLAMA_3_3_8B_INSTRUCT = 'us.meta.llama3-3-8b-instruct-v1:0', _('LLAMA_3_3_8B_INSTRUCT')
    MIXTRAL_8X70B_32768 = 'mixtral-8x7b-32768', _('MIXTRAL_8X70B_32768')
    GPT4_O = 'gpt-4o', _('GPT4_O')
    GPT4_O_MINI = 'gpt-4o-mini', _('GPT4_O_MINI')
    LLAMA_3_1_8B_OPS = 'meta-llama/Meta-Llama-3.1-8B-Instruct', _('meta-llama/Meta-Llama-3.1-8B-Instruct')
    GPT5_2 = 'gpt-5.2', _('GPT_5_2')
    GPT5_2_PRO = 'gpt-5.2-pro', _('GPT_5_2_PRO')
    GPT5_MINI = 'gpt-5-mini', _('GPT_5_MINI')


class EntityStatus(models.TextChoices):
    """
    Indicates whether an entity is active or inactive.
    Supports soft-deletion and visibility control.
    """
    ACTIVE = 'ACTIVE', _('ACTIVE')
    INACTIVE = 'INACTIVE', _('INACTIVE')


class ProfileType(models.TextChoices):
    """
    Defines different user profile roles.
    Used for access control and permissions.
    """
    USER = 'USER', _('USER')
    MODERATOR = 'MODERATOR', _('MODERATOR')
    PROSPECT = 'PROSPECT', _('PROSPECT')


class FeedbackChoices(models.TextChoices):
    """
    Captures feedback sentiment classification.
    Used for analytics and rating systems.
    """
    POSITIVE = 'POSITIVE', _('POSITIVE')
    NEGATIVE = 'NEGATIVE', _('NEGATIVE')


class GenderChoices(models.TextChoices):
    """
    Stores supported gender options.
    Used in user demographic information.
    """
    MALE = 'Male', _('Male')
    FEMALE = 'Female', _('Female')


class LanguageChoices(models.TextChoices):
    """
    Lists supported language-region codes.
    Used for localization and speech services.
    """
    INDIAN_ENGLISH = 'en-IN', _('INDIAN ENGLISH')
    INDIAN_HINDI = 'hi-IN', _('INDIAN HINDI')
    US_ENGLISH = 'en-US', _('US ENGLISH')
    INDIAN_KANNADA = 'kn-IN', _('INDIAN KANNADA')


class MediaTypeChoices(models.TextChoices):
    """
    Supported MIME types for uploaded media.
    Used for validation and content handling.
    """
    PDF = 'application/pdf', _('PDF')
    TXT = 'text/plain', _('TXT')
    CSV = 'text/csv', _('CSV')
    JPEG = 'image/jpeg', _('JPEG')
    PNG = 'image/png', _('PNG')
    SVG = 'image/svg+xml', _('SVG')
    WEBP = 'image/webp', _('WEBP')
    HEIF = 'image/heif', _('HEIF')
    HEIC = 'image/heic', _('HEIC')
    XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', _('XLSX')


class FileTypeChoices(models.TextChoices):
    """
    Supported document file types with utility helpers.
    Provides MIME, extension, and validation methods.
    """
    PDF = 'application/pdf', _('PDF')
    DOC = 'application/msword', _('DOC')
    DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', _('DOCX')
    TXT = 'text/plain', _('TXT')
    CSV = 'text/csv', _('CSV')
    XLS = 'application/vnd.ms-excel', _('XLS')
    XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', _('XLSX')


    @classmethod
    def get_extension_mapping(cls):
        """
        Returns mapping of MIME types to file extensions.
        Used for file naming and validation logic.
        """
        return {
            cls.PDF: '.pdf',
            cls.DOC: '.doc',
            cls.DOCX: '.docx',
            cls.TXT: '.txt',
            cls.CSV: '.csv',
            cls.XLS: '.xls',
            cls.XLSX: '.xlsx',
        }

    @classmethod
    def get_mime_from_extension(cls, extension):
        """
        Converts file extension into MIME type.
        Returns None if extension is unsupported.
        """
        ext = extension.lower().lstrip('.')
        ext_to_mime = {
            'pdf': cls.PDF,
            'doc': cls.DOC,
            'docx': cls.DOCX,
            'txt': cls.TXT,
            'csv': cls.CSV,
            'xls': cls.XLS,
            'xlsx': cls.XLSX,
        }
        return ext_to_mime.get(ext)

    @classmethod
    def get_label_from_extension(cls, extension):
        """
        Returns display label from file extension.
        Defaults to TXT label if unknown.
        """
        mime_type = cls.get_mime_from_extension(extension)
        if mime_type:
            return cls(mime_type).label
        return cls.TXT.label

    @classmethod
    def get_valid_extensions(cls):
        """
        Returns list of supported file extensions.
        Used for upload validation checks.
        """
        extension_mapping = cls.get_extension_mapping()
        return [ext.lstrip('.') for ext in extension_mapping.values()]

    @classmethod
    def is_valid_extension(cls, extension):
        """
        Validates if provided extension is supported.
        Returns True if valid, otherwise False.
        """
        ext = extension.lower().lstrip('.')
        return ext in cls.get_valid_extensions()


class VoiceProviderChoices(models.TextChoices):
    """
    Lists supported cloud voice providers.
    Used for speech-to-text and text-to-speech services.
    """
    AWS = 'aws', _('AWS')
    GCP = 'gcp', _('GCP')
    AZURE = 'azure', _('Azure')
    ELEVEN_LABS = 'eleven-labs', _('Eleven Labs')



class ChatStageChoices(models.TextChoices):
    """
    Represents predefined conversational stages in structured chat flows.
    Used in state-machine based bots to control progression.
    """
    WELCOME = 'Welcome_Strand', _('WELCOME_STRAND')
    ACHIEVEMENT_ORIENTATION = 'Achievement_Orientation', _('ACHIEVEMENT_ORIENTATION')
    COURAGE = 'Courage_Strand', _('COURAGE_STRAND')
    CONTINUOUS_LEARNING = 'Continuous_Strand', _('CONTINUOUS_STRAND')
    CRITICAL_THINKING = 'Critical_Thinking_Strand', _('CRITICAL_THINKING_STRAND')
    PURPOSE = 'Purpose_Strand', _('PURPOSE_STRAND')
    THANKYOU = 'Thank_You_Strand', _('THANK_YOU_STRAND')
    OTHER = 'Other', _('OTHER')


class TagChoices(models.TextChoices):
    """
    Defines moderation status for tags.
    Used in approval and publishing workflows.
    """
    APPROVED = 'Approved', _('Approved')
    PENDING = 'Pending', _('Pending')


class TagSourceChoices(models.TextChoices):
    """
    Identifies origin of a tag entry.
    Distinguishes manual and AI-based tagging.
    """
    MANUAL = 'MANUAL', _('Manual')
    AI_EXTRACTED = 'AI_EXTRACTED', _('AI Extracted')
    AI_GENERATED = 'AI_GENERATED', _('AI Generated')


class StoryLanguageChoices(models.TextChoices):
    """
    Lists supported languages for stories.
    Used for multilingual story management.
    """
    ENGLISH = 'en', _('English')
    HINDI = 'hi', _('Hindi')
    KANNADA = 'kn', _('Kannada')
    TELUGU = 'te', _('Telugu')
    ODIA = 'or', _('Odia')


class StorySourceChoices(models.TextChoices):
    """
    Specifies origin of story content.
    Tracks AI, user, or third-party sources.
    """
    AI_GENERATED = 'AI_GENERATED', _('AI_GENERATED')
    USER_GENERATED = 'USER_GENERATED', _('USER_GENERATED')
    THIRD_PARTY = 'THIRD_PARTY', _('THIRD_PARTY')


class StoryStatusChoices(models.TextChoices):
    """
    Represents lifecycle state of a story.
    Used to track processing and completion status.
    """
    PENDING = 'PENDING', _('PENDING')
    COMPLETED = 'COMPLETED', _('COMPLETED')


class EntityTypeChoices(models.TextChoices):
    """
    Marks whether an entity is mandatory or optional.
    Used in dynamic validation and schema enforcement.
    """
    MANDATORY = 'MANDATORY', _('MANDATORY')
    OPTIONAL = 'OPTIONAL', _('OPTIONAL')


class CompanyBotTypeChoices(models.TextChoices):
    """
    Defines architecture type of company bots.
    Determines conversation execution strategy.
    """
    SIMPLE = 'SIMPLE', _('SIMPLE')
    STATE_MACHINE = 'STATE_MACHINE', _('STATE_MACHINE')
    DATABASE_SIMPLE = 'DATABASE_SIMPLE', _('DATABASE_SIMPLE')
    INTERVIEW_STATE_MACHINE = 'INTERVIEW_STATE_MACHINE', _('INTERVIEW_STATE_MACHINE')


class BotStrategyChoices(models.TextChoices):
    ONESHOT = 'oneshot', _('One Shot')
    GUIDED_GUEST = 'guided_guest', _('Guided Guest')
    GUEST_DISCUSSION = 'guest_discussion', _('Guest Discussion')
    COMMON = 'common', _('Common')


class CompanyBotDynamicContextType(models.TextChoices):
    """
    Specifies dynamic context generation mechanism.
    Supports SQL queries or Python scripts.
    """
    SQL_QUERY = 'SQL_QUERY', _('SQL_QUERY')
    PYTHON_SCRIPT = 'PYTHON_SCRIPT', _('PYTHON_SCRIPT')


class CompanyChatSourceChoices(models.TextChoices):
    """
    Identifies source platform of a chat session.
    Used for analytics and usage tracking.
    """
    WEB = 'WEB', _('WEB')
    PHONE = 'PHONE', _('PHONE')


class RouteLanguageChoices(models.TextChoices):
    """
    Maps URL route prefixes to language codes.
    Used for multilingual routing configuration.
    """
    ENGLISH = 'en', _('/')
    HINDI = 'hi', _('/hindi')
    KANNADA = 'kn', _('/kannada')
    TELUGU = 'te', _('/telugu')
    ODIA = 'or', _('/odia')


class VoiceProvider(models.TextChoices):
    """
    Lists supported speech processing providers.
    Used for transcription and voice synthesis services.
    """
    GOOGLE = 'GOOGLE', _('GOOGLE')
    AI4Bharat = 'AI4Bharat', _('AI4Bharat')
    OPENAI_WHISPER = 'OPENAI_WHISPER', _('OpenAI Whisper')
    SARVAM = 'Sarvam', _('Sarvam')
    CUSTOM_LLM = 'CUSTOM_LLM', _('Custom LLM')


class VoiceType(models.TextChoices):
    """
    Defines type of voice processing operation.
    Covers STT, TTS, and transliteration modes.
    """
    SpeechToText = 'SpeechToText', _('Speech To Text')
    TextToText = 'TextToText', _('Text To Text')
    TextToSpeech = 'TextToSpeech', _('Text To Speech')
    Transliterate = 'Transliterate', _('Transliteration')


class LanguageMapping:
    """
    Utility class for region-based language mapping.
    Provides fallback if mapping is unavailable.
    """
    MAPPING = {
        "en": {"IN": "en-IN", "US": "en-US"},
        "hi": {"IN": "hi-IN"},
        "kn": {"IN": "kn-IN"},
        "te": {"IN": "te-IN"},
        "or": {"IN": "or-IN"},
    }

    @classmethod
    def get_mapped_language(cls, language_code: str, region: str = "IN") -> str:
        """
        Returns region-specific language code mapping.
        Defaults to '<code>-IN' if not found.
        """
        return cls.MAPPING.get(language_code, {}).get(region, f"{language_code}-IN")

    @classmethod
    def get_google_translate_language(cls, language_code: str, region: str = "IN") -> str:
        mapped = cls.get_mapped_language(language_code, region)
        return mapped.split("-")[0] if "-" in mapped else mapped

    @classmethod
    def get_sarvam_language(cls, language_code: str, region: str = "IN") -> str:
        normalized = (language_code or "").lower()
        if normalized in {"or", "od", "odia"}:
            return "od-IN"
        return cls.get_mapped_language(language_code, region)


class MediaTemplateChoices(models.TextChoices):
    """
    Defines supported media template formats.
    Used in content rendering workflows.
    """
    EJS = 'EJS', _('EJS')
    RAW_TEXT = 'RAW-TEXT', _('RAW-TEXT')


class PDFStrategyChoices(models.TextChoices):
    """
    Lists available PDF generation strategies.
    Determines rendering engine implementation.
    """
    HTMLPDF = 'HTMLPDF', _('HTMLPDF')
    PUPPETEER = 'PUPPETEER', _('PUPPETEER')
    HTMLDOCX = 'HTMLDOCX', _('HTMLDOCX')
    XLSX = 'XLSX', _('XLSX')


class SessionFlowName(models.TextChoices):
    """
    Represents predefined session flow identifiers.
    Used to control guest, login, and special flows.
    """
    GuestDiscussion = 'guest-discussion', _('guest-discussion')
    LoginDiscussion = 'login-discussion', _('login-discussion')
    GuestMiStory = 'guest-mi-story', _('guest-mi-story')
    SchoolSurvey = 'school-survey', _('school-survey')
    ListeningActivity = 'listening-activity', _('Listening Activity')
    LoginMiStory = 'login', _('login')
    SsoFlow = 'sso', _('sso')
    Reflection = 'reflection', _('reflection')
    megaPTM = 'megaPTM', _('Mega PTM')
    YLC = 'YLC', _('YLC')
    ParentPerceptionSurvey = 'parent_perception_survey', _('Parent Perception Survey')
    creation = 'creation', _('Creation')


class PreProcessType(models.TextChoices):
    """
    Defines preprocessing strategy before LLM execution.
    Controls prompt transformation complexity.
    """
    NONE = 'NONE', _('None')
    SIMPLE = 'SIMPLE', _('Simple Prompt')
    COMPLEX = 'COMPLEX', _('Use Preprocess Bot')


class PreProcessOutputMode(models.TextChoices):
    """
    Controls behavior after preprocessing stage.
    Can skip execution of the current stage.
    """
    NONE = 'NONE', 'None'
    SKIP = 'SKIP', 'Skip This Stage'
    MODIFY_QUESTION = 'MODIFY_QUESTION', 'Modify Bot Question'


class PostProcessType(models.TextChoices):
    """
    Defines postprocessing strategy after LLM response.
    Used for response refinement and enhancement.
    """
    NONE = 'NONE', _('None')
    SIMPLE = 'SIMPLE', _('Simple Prompt')
    COMPLEX = 'COMPLEX', _('Use Postprocess Bot')


class PostProcessOutputMode(models.TextChoices):
    """
    Controls workflow behavior after postprocessing.
    Can skip execution of the next stage.
    """
    NONE = 'NONE', 'None'
    SKIP = 'SKIP', 'Skip Next Stage'


class TextConversionType(models.TextChoices):
    """
    Specifies text transformation operation type.
    Supports translation and transliteration modes.
    """
    TRANSLATE = 'TRANSLATE', _('Translation')
    TRANSLITERATE = 'TRANSLITERATE', _('Transliteration')


class FileDisplayMode(models.TextChoices):
    """
    Controls file visibility scope and permissions.
    Determines access for UI and AI processing.
    """
    VISIBLE = "visible", _("Visible to All")
    AI_ONLY = "ai_only", _("AI Only (Hidden from UI)")
    PRIVATE = "private", _("Private (Hidden from UI and AI)")


class UserTypeChoices(models.TextChoices):
    GUEST = 'guest', _('Guest')
    AUTH = 'auth', _('Authenticated')
    ALL = 'all', _('All')


class CreateStoryChoices(models.TextChoices):
    ALL = 'all', _('All')
    NONE = 'none', _('None')


class LanguageOperationChoices(models.TextChoices):
    TRANSLATE = 'translate', _('Translate')
    TRANSLITERATE = 'transliterate', _('Transliterate')


class OperationTypeChoices(models.TextChoices):
    LLM = 'llm', _('LLM')
    NON_LLM = 'non_llm', _('Non-LLM')

