# mqtt_listener/models.py
from django.db import models
from django.utils import timezone

# Konstante für die Broadcast-ID
BROADCAST_NODE_ID_DEC = 4294967295

class Node(models.Model):
    node_id_dec = models.BigIntegerField(unique=True, null=True, blank=True, help_text="Dezimale Node ID des Ursprungsgeräts")
    node_id_hex = models.CharField(max_length=20, unique=True, null=True, blank=True, help_text="Hexadezimale Node ID (z.B. !abcdef12)")
    long_name = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    short_name = models.CharField(max_length=20, blank=True, null=True)
    hardware_model_str = models.CharField(max_length=50, blank=True, null=True) # Beibehalten als String wie im Original
    role_str = models.CharField(max_length=50, blank=True, null=True) # Beibehalten als String wie im Original
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_display_name(self):
        """Liefert den besten verfügbaren Namen oder die Hex-ID für die Anzeige."""
        if self.long_name:
            return self.long_name
        if self.short_name:
            return self.short_name
        if self.node_id_hex:
            return self.node_id_hex
        if self.node_id_dec is not None:
            return f"!{self.node_id_dec:x}" # Fallback auf Hex-Konvertierung der Dezimal-ID
        return f"Node {self.pk}"

    def __str__(self):
        return self.get_display_name()

    def get_identifier(self): # Nützlich für URLs
        return self.node_id_hex if self.node_id_hex else str(self.node_id_dec)


    class Meta:
        ordering = ['long_name', 'node_id_hex']


class MessagePacket(models.Model):
    packet_hash = models.CharField(max_length=64, unique=True, help_text="Eindeutiger Hash des Roh-Pakets zur Vermeidung von Duplikaten")
    timestamp_mqtt = models.DateTimeField(default=timezone.now, db_index=True, help_text="Zeitstempel des MQTT-Paketempfangs (UTC)")
    topic = models.CharField(max_length=255)

    from_node = models.ForeignKey(Node, related_name='sent_packets', on_delete=models.SET_NULL, null=True, blank=True, help_text="Ursprünglicher Absender (aus 'from')")
    to_node_id_dec = models.BigIntegerField(null=True, blank=True, help_text="Ziel Node ID (aus 'to')") # ^all ist 4294967295
    sender_node = models.ForeignKey(Node, related_name='relayed_packets', on_delete=models.SET_NULL, null=True, blank=True, help_text="Direkter Sender/Repeater (aus 'sender')")

    channel_id = models.IntegerField(null=True, blank=True, help_text="Channel ID aus dem Topic")
    gateway_id_hex = models.CharField(max_length=20, null=True, blank=True, help_text="Gateway ID aus dem Topic (z.B. !e69a833c)")

    rssi_mqtt = models.IntegerField(null=True, blank=True, help_text="RSSI des Gateways zum Node (aus 'rssi')")
    snr_mqtt = models.FloatField(null=True, blank=True, help_text="SNR des Gateways zum Node (aus 'snr')")
    hops_away_mqtt = models.IntegerField(null=True, blank=True, help_text="Hops vom Gateway (aus 'hops_away')")
    hop_limit = models.IntegerField(null=True, blank=True)
    hop_start = models.IntegerField(null=True, blank=True)

    message_type = models.CharField(max_length=50, blank=True, null=True, db_index=True, help_text="Typ aus dem JSON (z.B. position, telemetry, text)")
    raw_json_payload = models.JSONField(help_text="Die gesamte JSON-Payload der Nachricht")

    @property
    def is_broadcast(self):
        return self.to_node_id_dec == BROADCAST_NODE_ID_DEC

    def get_recipient_display(self):
        if self.is_broadcast:
            return "Broadcast"
        if self.to_node_id_dec is not None:
            try:
                recipient_node = Node.objects.get(node_id_dec=self.to_node_id_dec)
                return recipient_node.get_display_name()
            except Node.DoesNotExist:
                # Fallback: Konvertiere die Dezimal-ID zu Hex mit '!' Präfix
                return f"!{self.to_node_id_dec:x}"
        return "N/A" # Kein spezifischer Empfänger und kein Broadcast

    class Meta:
        ordering = ['-timestamp_mqtt']
        indexes = [
            models.Index(fields=['from_node', 'message_type']),
        ]

    def __str__(self):
        return f"{self.message_type or 'ACK'} from {self.from_node} to {self.get_recipient_display()} at {self.timestamp_mqtt.strftime('%Y-%m-%d %H:%M:%S')}"


class Position(models.Model):
    packet = models.OneToOneField(MessagePacket, on_delete=models.CASCADE, related_name='position_data')
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.IntegerField(null=True, blank=True)
    precision_bits = models.IntegerField(null=True, blank=True)
    sats_in_view = models.IntegerField(null=True, blank=True)
    pdop = models.FloatField(null=True, blank=True)
    timestamp_device = models.DateTimeField(null=True, blank=True, help_text="Zeitstempel der Position vom Gerät (UTC)")

    def __str__(self):
        return f"Position for {self.packet.from_node} ({self.latitude:.5f}, {self.longitude:.5f})"

class Telemetry(models.Model):
    packet = models.OneToOneField(MessagePacket, on_delete=models.CASCADE, related_name='telemetry_data')
    battery_level = models.IntegerField(null=True, blank=True)
    voltage = models.FloatField(null=True, blank=True, help_text="Spannung in Volt")
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    air_util_tx = models.FloatField(null=True, blank=True, help_text="Als Dezimal, z.B. 0.05 für 5%")
    channel_utilization = models.FloatField(null=True, blank=True, help_text="Als Dezimal, z.B. 0.1 für 10%")

    def __str__(self):
        return f"Telemetry for {self.packet.from_node}"

class TextMessage(models.Model):
    packet = models.OneToOneField(MessagePacket, on_delete=models.CASCADE, related_name='text_message_data')
    text = models.TextField()

    def __str__(self):
        return f"Text from {self.packet.from_node}: {self.text[:50]}"