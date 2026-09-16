from django.contrib import admin
from chatbot.models import Story


class UserNameFilter(admin.SimpleListFilter):
    title = 'User Name'
    parameter_name = 'user_name'

    def lookups(self, request, model_admin):
        user_names = (
            Story.objects.exclude(other_params__user_name__isnull=True)
            .values_list('other_params__user_name', flat=True)
            .distinct()
        )
        return [(name, name) for name in user_names if name]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(other_params__user_name=self.value())
        return queryset