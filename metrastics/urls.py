from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/', include('metrastics_dashboard.urls')),
    path('commander/', include('metrastics_commander.urls')), # Added Commander URLs
    path('', include('metrastics_dashboard.urls')), # Optionally, make dashboard the root
]