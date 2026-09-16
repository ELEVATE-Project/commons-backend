from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from shikshalokam.models.wishlist_model import ProjectWishlist


@admin.register(ProjectWishlist)
class ProjectWishlistAdmin(admin.ModelAdmin):
    list_display = ('project', 'author', 'created_at')
    list_filter = (CustomAdvanceDateFilter, 'project__id', 'author')

    raw_id_fields = ('project', 'author')
