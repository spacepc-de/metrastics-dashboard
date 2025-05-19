from django.apps import AppConfig


class MqttListenerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mqtt_listener'
