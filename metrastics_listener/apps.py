# metrastics_listener/apps.py
import os
import threading
from django.apps import AppConfig
from django.core.management import call_command
from django.conf import settings # Added settings

class MetrasticsListenerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'metrastics_listener'

    def ready(self):
        """
        Wird aufgerufen, wenn die Anwendung vollständig geladen ist.
        Startet hier den listen_device Management-Befehl in einem separaten Thread.
        """
        # Verhindern, dass der Befehl vom Auto-Reloader doppelt ausgeführt wird
        # oder wenn DEBUG False ist (Produktionsähnlicher Modus)
        # RUN_MAIN wird von Django gesetzt, wenn der Server startet (nicht der Reloader).
        # In einer Produktionsumgebung (DEBUG=False) wollen wir den Listener ebenfalls starten.
        should_run_listener = os.environ.get('RUN_MAIN') or not settings.DEBUG

        if should_run_listener:
            print("Attempting to start listen_device command in a new thread...")
            try:
                thread = threading.Thread(target=call_command, args=('listen_device',), daemon=True)
                thread.start()
                print("listen_device command started in a separate thread.")
            except Exception as e:
                print(f"Failed to start listen_device command: {e}")
        else:
            if not os.environ.get('RUN_MAIN'):
                print("Skipping listen_device start in reloader process.")
            if settings.DEBUG and not os.environ.get('RUN_MAIN'):
                 pass # Expected behaviour in debug with reloader
            elif not settings.DEBUG:
                 # This case should ideally not be hit if logic is sound, but as a fallback.
                 print("Skipping listen_device start (settings.DEBUG is False but RUN_MAIN not set).")