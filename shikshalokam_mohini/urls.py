"""
URL configuration for shikshalokam_mohini project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.documentation import include_docs_urls
from shikshalokam.views import health_views
from chatbot.views import aws_views


admin.site.site_header = 'Mohini Admin Panel'


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_views.health_check, name='health_check'),
    path('docs/', include_docs_urls(title='API Documentation')),
    path('api/shikshalokam/', include('shikshalokam.urls')),
    re_path(r'^api/storage/upload-local/(?P<object_key>.+)$', aws_views.upload_media_local, name='upload_media_local'),
    path("", include("chatbot.urls", namespace="chatbot")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
