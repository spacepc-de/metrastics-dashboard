# metrastics_commander/models.py
from django.db import models
from django.utils import timezone

class CommanderRule(models.Model):
    MATCH_TYPE_CHOICES = [
        ('exact', 'Exakte Übereinstimmung'),
        ('contains', 'Enthält (Groß-/Kleinschreibung ignorieren)'),
        ('startswith', 'Beginnt mit (Groß-/Kleinschreibung ignorieren)'),
        ('regex', 'Regulärer Ausdruck'),
    ]

    name = models.CharField(max_length=100, unique=True, help_text="Ein eindeutiger Name für diese Regel.")
    trigger_phrase = models.TextField(help_text="Die Phrase oder das Muster, das diese Regel auslöst.")
    match_type = models.CharField(
        max_length=15,
        choices=MATCH_TYPE_CHOICES,
        default='contains',
        help_text="Wie die trigger_phrase mit der eingehenden Nachricht abgeglichen werden soll."
    )
    response_template = models.TextField(
        help_text="Die Antwortvorlage. Verwenden Sie Platzhalter wie <SENDER_LONG_NAME>, <SENDER_LATITUDE>, <SENDER_LONGITUDE>, <RECEIVED_MESSAGE_TEXT>, etc."
    )
    enabled = models.BooleanField(default=True, help_text="Ist diese Regel aktiv?")
    cooldown_seconds = models.PositiveIntegerField(
        default=60,
        help_text="Minimale Zeit in Sekunden, bevor diese Regel für denselben Absenderknoten erneut ausgelöst wird. 0 für keinen Cooldown."
    )
    # Stores last trigger time for each node_id to manage cooldowns
    # Format: {"!nodeid1": "iso_timestamp", "!nodeid2": "iso_timestamp"}
    last_triggered_for_nodes = models.JSONField(default=dict, blank=True, help_text="Zeitstempel der letzten Auslösung pro Knoten-ID für Cooldown-Management.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Commander Regel"
        verbose_name_plural = "Commander Regeln"


class CommanderSettings(models.Model):
    """Singleton model to store commander-wide settings."""
    chatbot_mode_enabled = models.BooleanField(
        default=False,
        help_text="Wenn aktiviert, werden alle Nachrichten direkt an ChatGPT weitergeleitet.",
    )

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Commander Einstellungen"

    class Meta:
        verbose_name = "Commander Einstellung"
        verbose_name_plural = "Commander Einstellungen"