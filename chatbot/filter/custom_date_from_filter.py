from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class CustomAdvanceDateFilter(admin.SimpleListFilter):
    """
    Neet to use this filter If we want to see the calendar based Date filter. Lookup function should have this value
    so that the filter is visible (but the value can be anything in that format)
    QuerySet is there just for override purpose.
    """


    title = _('From Date')
    parameter_name = 'created_at_from'

    def lookups(self, request, model_admin):
        return [
            ('Pick From Date', _('Pick From Date'))
        ]

    def queryset(self, request, queryset):
        return None

