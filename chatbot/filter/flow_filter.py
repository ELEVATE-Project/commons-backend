from django.contrib.admin import SimpleListFilter

from chatbot.models import SessionFlowName


class FlowFilter(SimpleListFilter):
    title = 'Flow'
    parameter_name = 'flow'

    def lookups(self, request, model_admin):
        return [(choice.value, choice.label) for choice in SessionFlowName]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(other_params__flow=self.value())
        return queryset
