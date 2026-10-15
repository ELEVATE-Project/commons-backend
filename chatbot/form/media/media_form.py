from django import forms
from django.contrib import admin
from chatbot.models.media_models import Media, Tag
from chatbot.models import TagSourceChoices, TagChoices

BOT_PROFILE_ID = 1


class MediaAdminForm(forms.ModelForm):
    manual_tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("Manual Tags", is_stacked=False)
    )
    auto_tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("Auto Tags", is_stacked=False),
        # disabled=True
    )

    class Meta:
        model = Media
        fields = '__all__'
        exclude = ['tags']  # Exclude the original tags field since we're handling it manually

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Manual tags: Include ALL manual tags from ALL organizations
        self.fields['manual_tags'].queryset = Tag.objects.filter(
            source_type=TagSourceChoices.MANUAL,
            status=TagChoices.APPROVED
        ).order_by('name')
        # No company filter - shared across all organizations

        if getattr(self.instance, 'pk', None):
            # Existing instance - set initial values
            self.fields['manual_tags'].initial = self.instance.tags.filter(
                source_type=TagSourceChoices.MANUAL
            )

            # Auto tags: Include ALL AI-extracted tags from ALL organizations
            if hasattr(self.instance, '_auto_tags_to_preserve'):
                auto_qs = self.instance._auto_tags_to_preserve
            else:
                auto_qs = self.instance.tags.filter(
                    source_type__in=[TagSourceChoices.AI_EXTRACTED, TagSourceChoices.AI_GENERATED]
                )

            if auto_qs.exists() if hasattr(auto_qs, 'exists') else auto_qs:
                # Show all AI tags from all organizations in the dropdown
                self.fields['auto_tags'].queryset = Tag.objects.filter(
                    source_type__in=[TagSourceChoices.AI_EXTRACTED, TagSourceChoices.AI_GENERATED],
                    status=TagChoices.APPROVED
                ).order_by('name')
                # No company filter - shared across all organizations

                self.fields['auto_tags'].initial = auto_qs
            else:
                self.fields.pop('auto_tags')
        else:
            # New object → hide auto_tags field
            self.fields.pop('auto_tags', None)

    def save(self, commit=True):
        # Save instance first to ensure it has an ID
        instance = super().save(commit=False)
        manual_tags = list(self.cleaned_data.get('manual_tags', []))
        print("manual_tags: ", manual_tags)

        if commit:
            # For existing instances, preserve existing auto tags
            auto_tags = list(instance.tags.filter(
                source_type__in=[TagSourceChoices.AI_EXTRACTED, TagSourceChoices.AI_GENERATED]
            ))
        else:
            auto_tags = list(self.cleaned_data.get('auto_tags', []))
        print("auto_tags: ", auto_tags)

        if commit:
            print("Commit is True")
            instance.save()  # Now instance.pk exists
            print("Cleaned Data: ", self.cleaned_data)

            # Set all tags (manual + auto)
            instance.tags.set(manual_tags + auto_tags)
        else:
            print("Commit is False")
            # Even if not committing, attach manual tags to the instance's m2m cache
            instance._manual_tags_to_set = manual_tags
            instance._auto_tags_to_preserve = auto_tags

        print("Instance: ", instance)
        return instance
