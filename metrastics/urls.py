# metrastics/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Provide a unique instance namespace for the '/dashboard/' path
    path('dashboard/', include('metrastics_dashboard.urls', namespace='dashboard_main')),
    path('commander/', include('metrastics_commander.urls')),
    # Provide another unique instance namespace for the root '' path
    path('', include('metrastics_dashboard.urls', namespace='dashboard_root')),
]