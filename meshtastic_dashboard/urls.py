# meshtastic_dashboard/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('mqtt_listener.urls')), # Leitet zur App weiter
]