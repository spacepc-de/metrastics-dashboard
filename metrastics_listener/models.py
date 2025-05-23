# metrastics_listener/models.py
from django.db import models
from django.utils import timezone # Import timezone für ListenerState


# from django.contrib.auth.models import User # Für Benutzerauthentifizierung, falls später benötigt

class Node(models.Model):
    node_id = models.CharField(max_length=24, primary_key=True, help_text="Knoten-ID (z.B. !aabbccdd)")
    node_num = models.PositiveIntegerField(unique=True, null=True, blank=True,
                                           help_text="Knotennummer (ganzzahlige Darstellung der ID)")

    long_name = models.CharField(max_length=100, null=True, blank=True)
    short_name = models.CharField(max_length=20, null=True, blank=True)
    macaddr = models.CharField(max_length=17, null=True, blank=True,
                               help_text="MAC-Adresse im Format XX:XX:XX:XX:XX:XX")
    hw_model = models.CharField(max_length=50, null=True, blank=True, help_text="Hardware-Modell des Knotens")

    firmware_version = models.CharField(max_length=30, null=True, blank=True)
    role = models.CharField(max_length=30, null=True, blank=True,
                            help_text="Rolle des Knotens im Netzwerk (z.B. ROUTER, CLIENT)")
    is_local = models.BooleanField(default=False, help_text="Gibt an, ob dies der lokale Knoten ist")

    last_heard = models.FloatField(null=True, blank=True, help_text="Unix-Zeitstempel des letzten empfangenen Pakets")

    battery_level = models.PositiveIntegerField(null=True, blank=True,
                                                help_text="Batteriestand in Prozent (0-100), oder 255 für unbekannt/strombetrieben")
    voltage = models.FloatField(null=True, blank=True, help_text="Batteriespannung in Volt")
    channel_utilization = models.FloatField(null=True, blank=True, help_text="Kanal-Auslastung in Prozent")
    air_util_tx = models.FloatField(null=True, blank=True, help_text="Luftschnittstellen-Auslastung (TX) in Prozent")
    uptime_seconds = models.PositiveIntegerField(null=True, blank=True, help_text="Betriebszeit des Geräts in Sekunden")

    snr = models.FloatField(null=True, blank=True, help_text="Signal-Rausch-Verhältnis des letzten Pakets")
    rssi = models.IntegerField(null=True, blank=True,
                               help_text="Empfangssignalstärke des letzten Pakets (typischerweise negativ)")

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.IntegerField(null=True, blank=True, help_text="Höhe über dem Meeresspiegel in Metern")
    position_time = models.FloatField(null=True, blank=True, help_text="Unix-Zeitstempel des letzten Positionsupdates")

    telemetry_time = models.FloatField(null=True, blank=True,
                                       help_text="Unix-Zeitstempel des letzten Telemetrie-Updates")

    user_info = models.JSONField(null=True, blank=True, help_text="Rohe Benutzerinformationen als JSON vom Paket")
    position_info = models.JSONField(null=True, blank=True, help_text="Rohe Positionsinformationen als JSON vom Paket")
    device_metrics_info = models.JSONField(null=True, blank=True,
                                           help_text="Rohe Gerätemetriken als JSON von Telemetrie")
    environment_metrics_info = models.JSONField(null=True, blank=True,
                                                help_text="Rohe Umgebungsmetriken als JSON von Telemetrie")
    module_config_info = models.JSONField(null=True, blank=True,
                                          help_text="Rohe Modulkonfiguration als JSON von Knoteninfo")
    channel_info = models.JSONField(null=True, blank=True, help_text="Rohe Kanalinformationen als JSON von Knoteninfo")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.long_name or self.short_name or self.node_id} ({self.node_id})"

    class Meta:
        ordering = ['node_num', 'node_id']
        verbose_name = "Node"
        verbose_name_plural = "Nodes"


class Packet(models.Model):
    event_id = models.CharField(max_length=50, unique=True, help_text="Eindeutiger Bezeichner für das Paketereignis")
    timestamp = models.FloatField(help_text="Unix-Zeitstempel des Paketempfangs/-verarbeitung")
    rx_time = models.BigIntegerField(null=True, blank=True, help_text="RX-Zeit des Geräts, falls verfügbar (Unix)")

    from_node = models.ForeignKey(Node, related_name='sent_packets', on_delete=models.SET_NULL, null=True, blank=True,
                                  to_field='node_id')
    to_node = models.ForeignKey(Node, related_name='received_packets', on_delete=models.SET_NULL, null=True, blank=True,
                                to_field='node_id')

    from_node_id_str = models.CharField(max_length=24, null=True, blank=True, db_index=True,
                                        help_text="String-ID des Absenderknotens")
    to_node_id_str = models.CharField(max_length=24, null=True, blank=True, db_index=True,
                                      help_text="String-ID des Empfängerknotens (kann ^all sein)")

    channel = models.IntegerField(null=True, blank=True, help_text="Meshtastic-Kanalindex, auf dem das Paket war")
    portnum = models.CharField(max_length=50, null=True, blank=True, help_text="Portnum-Name (z.B. TEXT_MESSAGE_APP)")

    packet_type = models.CharField(max_length=50, null=True, blank=True, db_index=True,
                                   help_text="Anwendungsbezogener Pakettyp (z.B. Message, Position)")

    rx_snr = models.FloatField(null=True, blank=True)
    rx_rssi = models.IntegerField(null=True, blank=True)
    hop_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    want_ack = models.BooleanField(default=False)

    decoded_json = models.JSONField(null=True, blank=True, help_text="Dekodierte Nutzlast als JSON")
    raw_json = models.JSONField(null=True, blank=True, help_text="Rohe Paketstruktur als JSON")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Packet {self.event_id} von {self.from_node_id_str or 'N/A'} an {self.to_node_id_str or 'N/A'}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['packet_type']),
        ]
        verbose_name = "Packet"
        verbose_name_plural = "Packets"


class Message(models.Model):
    packet = models.OneToOneField(Packet, on_delete=models.CASCADE, primary_key=True, related_name="message_content")

    from_node = models.ForeignKey(Node, related_name='sent_messages', on_delete=models.SET_NULL, null=True, blank=True,
                                  to_field='node_id')
    to_node = models.ForeignKey(Node, related_name='received_messages', on_delete=models.SET_NULL, null=True,
                                blank=True, to_field='node_id')
    from_node_id_str = models.CharField(max_length=24, null=True, blank=True, db_index=True)
    to_node_id_str = models.CharField(max_length=24, null=True, blank=True, db_index=True)

    channel = models.IntegerField(null=True, blank=True,
                                  help_text="Ursprüngliche interne Meshtastic-Kanal-ID, auf dem die Nachricht gesendet wurde")
    text = models.TextField()
    timestamp = models.FloatField(help_text="Unix-Zeitstempel (identisch mit Paket)")

    rx_snr = models.FloatField(null=True, blank=True)
    rx_rssi = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Nachricht von {self.from_node_id_str or 'N/A'} an {self.to_node_id_str or 'N/A'}: {self.text[:50]}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Message"
        verbose_name_plural = "Messages"


class Position(models.Model):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='positions', to_field='node_id')
    timestamp = models.FloatField(help_text="Unix-Zeitstempel des Positionsupdates")
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.IntegerField(null=True, blank=True, help_text="Höhe über dem Meeresspiegel in Metern")

    precision_bits = models.PositiveIntegerField(null=True, blank=True)
    ground_speed = models.PositiveIntegerField(null=True, blank=True,
                                               help_text="Geschwindigkeit in m/s oder Knoten (geräteabhängig)")
    ground_track = models.PositiveIntegerField(null=True, blank=True, help_text="Kurs über Grund in Grad")
    sats_in_view = models.PositiveSmallIntegerField(null=True, blank=True)

    pdop = models.FloatField(null=True, blank=True)
    hdop = models.FloatField(null=True, blank=True)
    vdop = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Position für {self.node_id} um {self.timestamp}: ({self.latitude}, {self.longitude})"

    class Meta:
        ordering = ['node', '-timestamp']
        indexes = [models.Index(fields=['node', '-timestamp'])]
        verbose_name = "Position"
        verbose_name_plural = "Positions"


class Telemetry(models.Model):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='telemetry_updates', to_field='node_id')
    timestamp = models.FloatField(help_text="Unix-Zeitstempel des Telemetrie-Updates")

    battery_level = models.PositiveIntegerField(null=True, blank=True)
    voltage = models.FloatField(null=True, blank=True)
    channel_utilization = models.FloatField(null=True, blank=True)
    air_util_tx = models.FloatField(null=True, blank=True)
    uptime_seconds = models.PositiveIntegerField(null=True, blank=True)

    temperature = models.FloatField(null=True, blank=True, help_text="Grad Celsius")
    relative_humidity = models.FloatField(null=True, blank=True, help_text="Prozent")
    barometric_pressure = models.FloatField(null=True, blank=True, help_text="hPa")
    gas_resistance = models.FloatField(null=True, blank=True, help_text="Ohm")
    iaq = models.FloatField(null=True, blank=True, help_text="Index für Luftqualität")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telemetrie für {self.node_id} um {self.timestamp}"

    class Meta:
        ordering = ['node', '-timestamp']
        indexes = [models.Index(fields=['node', '-timestamp'])]
        verbose_name = "Telemetry"
        verbose_name_plural = "Telemetry Data"


class AverageMetricsHistory(models.Model):
    timestamp = models.FloatField(unique=True, help_text="Unix-Zeitstempel der Metrikberechnung")
    average_snr = models.FloatField(null=True, blank=True)
    average_rssi = models.FloatField(null=True, blank=True)
    average_battery = models.FloatField(null=True, blank=True)
    average_chan_util = models.FloatField(null=True, blank=True)
    average_air_util_tx = models.FloatField(null=True, blank=True)
    active_node_count = models.PositiveIntegerField()
    total_node_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Durchschnittsmetriken um {self.timestamp} ({self.active_node_count}/{self.total_node_count} Knoten)"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Average Metrics History"
        verbose_name_plural = "Average Metrics Histories"


class Traceroute(models.Model):
    packet = models.OneToOneField(Packet, on_delete=models.CASCADE, related_name="traceroute_info", null=True,
                                  blank=True)
    packet_event_id = models.CharField(max_length=50, unique=True,
                                       help_text="Korrespondierende Paket-event_id, falls verknüpft")

    requester_node = models.ForeignKey(Node, related_name='sent_traceroutes', on_delete=models.SET_NULL, null=True,
                                       blank=True, to_field='node_id')
    responder_node = models.ForeignKey(Node, related_name='received_traceroutes', on_delete=models.SET_NULL, null=True,
                                       blank=True, to_field='node_id')
    requester_node_id_str = models.CharField(max_length=24, null=True, blank=True)
    responder_node_id_str = models.CharField(max_length=24, null=True, blank=True)

    route_json = models.JSONField(help_text="Liste der Knotennummern (Integer) im Pfad")
    timestamp = models.FloatField(help_text="Unix-Zeitstempel des Traceroute-Ergebnisses")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Traceroute von {self.requester_node_id_str} zu {self.responder_node_id_str} um {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Traceroute"
        verbose_name_plural = "Traceroutes"


class ScheduledTask(models.Model):
    nodeId = models.CharField(max_length=24, help_text="Zielknoten-ID für die Aufgabe (z.B. !aabbccdd oder ^all)")
    taskType = models.CharField(max_length=50, help_text="Aufgabentyp (z.B. message, website_monitor)")
    actionPayload = models.TextField(null=True, blank=True, help_text="JSON- oder String-Nutzlast für die Aktion")
    cronString = models.CharField(max_length=100, help_text="Cron-ähnlicher String für die Zeitplanung")
    enabled = models.BooleanField(default=True)

    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Aufgabe {self.id}: {self.taskType} für {self.nodeId} ({'Aktiviert' if self.enabled else 'Deaktiviert'})"

    class Meta:
        ordering = ['-createdAt']
        verbose_name = "Scheduled Task"
        verbose_name_plural = "Scheduled Tasks"


class AutoReplyRule(models.Model):
    trigger_phrase = models.TextField(help_text="Auslösende Phrase oder Regex-Muster.")
    MATCH_TYPE_CHOICES = [
        ('contains', 'Enthält'),
        ('exact', 'Exakte Übereinstimmung'),
        ('regex', 'Regulärer Ausdruck'),
    ]
    match_type = models.CharField(max_length=10, choices=MATCH_TYPE_CHOICES, help_text="Art des Abgleichs der Phrase.")
    response_message = models.TextField(help_text="Die zu sendende Antwortnachricht.")
    cooldown_seconds = models.PositiveIntegerField(default=60,
                                                   help_text="Minimale Zeit in Sekunden, bevor diese Regel für denselben Absender erneut ausgelöst wird.")
    is_enabled = models.BooleanField(default=True, help_text="Gibt an, ob die Regel aktiv ist.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AutoReply Regel {self.id}: '{self.trigger_phrase}' ({self.match_type})"

    class Meta:
        ordering = ['id']
        verbose_name = "Auto-Reply Rule"
        verbose_name_plural = "Auto-Reply Rules"


class ListenerState(models.Model):
    STATUS_CHOICES = [
        ('INITIALIZING', 'Initializing'),
        ('CONNECTING', 'Connecting'),
        ('CONNECTED', 'Connected'),
        ('DISCONNECTED', 'Disconnected'),
        ('ERROR', 'Error'),
        ('UNKNOWN', 'Unknown'), # Default fallback
    ]
    # Use a fixed primary key to ensure only one row for the listener state (singleton pattern)
    singleton_id = models.PositiveIntegerField(primary_key=True, default=1, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNKNOWN')
    last_error_message = models.TextField(null=True, blank=True)
    local_node_id = models.CharField(max_length=24, null=True, blank=True)
    local_node_num = models.PositiveIntegerField(null=True, blank=True)
    local_node_name = models.CharField(max_length=100, null=True, blank=True)
    local_node_channel_map_json = models.JSONField(null=True, blank=True, help_text="JSON representation of the channel map")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Listener Status: {self.get_status_display()}"

    class Meta:
        verbose_name = "Listener State"
        verbose_name_plural = "Listener States" # Or just "Listener State" if only one row