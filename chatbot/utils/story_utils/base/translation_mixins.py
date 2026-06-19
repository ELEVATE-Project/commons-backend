from chatbot.models import StoryTranslation


class LanguageDetectionMixin:
    """Mixin for consistent language detection across serializers and views"""

    def detect_language(self, request, instance=None):
        """Detect language using consistent logic"""
        language = (
                request.query_params.get('language') or
                request.META.get('HTTP_X_LANGUAGE') or
                self._extract_language_from_accept_header(request)
        )

        if not language and instance:
            print("Checking for fallback langugaeg")
            translation_languages = list(instance.translations.values_list('language', flat=True))
            if translation_languages:
                language = translation_languages[0]
            else:
                language = 'en'

        return language or 'en'

    def _extract_language_from_accept_header(self, request):
        """Extract language from Accept-Language header"""
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        if accept_language:
            languages = []
            for lang_part in accept_language.split(','):
                lang = lang_part.strip().split(';')[0].split('-')[0]
                if lang and lang != 'en':
                    languages.append(lang)
            return languages[0] if languages else None
        return None


class TranslationMixin(LanguageDetectionMixin):
    """Mixin to handle story translations in serializers"""

    def apply_translation(self, data, instance):
        """Apply translation to story data based on request language"""
        request = self.context.get('request')
        if not request:
            return data

        language = self.detect_language(request, instance)

        if language == 'en' or instance.language == language:
            return data

        try:
            translation = instance.translations.get(language=language)

            data['title'] = translation.title
            if translation.content:
                data['content'] = translation.content
            if translation.blurb:
                data['blurb'] = translation.blurb
            if translation.tweet:
                data['tweet'] = translation.tweet
            if translation.objective:
                data['objective'] = translation.objective
            if translation.action_steps:
                data['action_steps'] = translation.action_steps
            if translation.impact:
                data['impact'] = translation.impact
            if translation.micro_improvement:
                data['micro_improvement'] = translation.micro_improvement
            if translation.formatted_content:
                data['formatted_content'] = translation.formatted_content

            if translation.other_params and data['other_params']:
                data['other_params'].update(translation.other_params)
            elif translation.other_params:
                data['other_params'] = translation.other_params

        except StoryTranslation.DoesNotExist:
            pass

        return data
