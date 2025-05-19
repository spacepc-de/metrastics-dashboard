# mqtt_listener/admin.py
from django.contrib import admin
from .models import Node, MessagePacket, Position, Telemetry, TextMessage

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('long_name', 'short_name', 'node_id_dec', 'node_id_hex', 'hardware_model_str', 'role_str', 'updated_at')
    search_fields = ('long_name', 'node_id_dec', 'node_id_hex')
    list_filter = ('hardware_model_str', 'role_str', 'updated_at')

@admin.register(MessagePacket)
class MessagePacketAdmin(admin.ModelAdmin):
    list_display = ('timestamp_mqtt', 'message_type', 'from_node_display', 'to_node_id_dec', 'sender_node_display', 'rssi_mqtt', 'snr_mqtt', 'topic_short')
    list_filter = ('message_type', 'timestamp_mqtt', 'channel_id')
    search_fields = ('from_node__long_name', 'from_node__node_id_hex', 'sender_node__long_name', 'topic')
    raw_id_fields = ('from_node', 'sender_node') # Für bessere Performance bei vielen Nodes
    readonly_fields = ('packet_hash', 'raw_json_payload_pretty') # raw_json_payload kann sehr groß sein

    def from_node_display(self, obj):
        return str(obj.from_node) if obj.from_node else None
    from_node_display.short_description = 'From Node'

    def sender_node_display(self, obj):
        return str(obj.sender_node) if obj.sender_node else None
    sender_node_display.short_description = 'Via/Sender Node'

    def topic_short(self,obj):
        return obj.topic[:50] + '...' if len(obj.topic) > 50 else obj.topic
    topic_short.short_description = 'Topic'

    def raw_json_payload_pretty(self, obj):
        import json
        from django.utils.html import format_html
        pretty_json = json.dumps(obj.raw_json_payload, indent=2)
        return format_html("<pre>{}</pre>", pretty_json)
    raw_json_payload_pretty.short_description = 'Raw JSON (Formatted)'


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('packet_link', 'latitude', 'longitude', 'altitude', 'timestamp_device')
    raw_id_fields = ('packet',)
    search_fields = ('packet__from_node__long_name', 'packet__from_node__node_id_hex')
    list_filter = ('timestamp_device',)

    def packet_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        link = reverse("admin:mqtt_listener_messagepacket_change", args=[obj.packet.id])
        return format_html('<a href="{}">{}</a>', link, f"Packet from {obj.packet.from_node}")
    packet_link.short_description = 'Message Packet'


@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ('packet_link', 'battery_level', 'voltage', 'uptime_readable')
    raw_id_fields = ('packet',)

    def packet_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        link = reverse("admin:mqtt_listener_messagepacket_change", args=[obj.packet.id])
        return format_html('<a href="{}">{}</a>', link, f"Packet from {obj.packet.from_node}")
    packet_link.short_description = 'Message Packet'

    def uptime_readable(self, obj):
        if obj.uptime_seconds is None: return "N/A"
        days = obj.uptime_seconds // (24 * 3600)
        remainder = obj.uptime_seconds % (24 * 3600)
        hours = remainder // 3600
        remainder %= 3600
        minutes = remainder // 60
        seconds = remainder % 60
        return f"{days}d {hours}h {minutes}m {seconds}s"
    uptime_readable.short_description = 'Uptime'


@admin.register(TextMessage)
class TextMessageAdmin(admin.ModelAdmin):
    list_display = ('packet_link', 'text_preview')
    raw_id_fields = ('packet',)
    search_fields = ('text', 'packet__from_node__long_name')

    def packet_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        link = reverse("admin:mqtt_listener_messagepacket_change", args=[obj.packet.id])
        return format_html('<a href="{}">{}</a>', link, f"Packet from {obj.packet.from_node}")
    packet_link.short_description = 'Message Packet'

    def text_preview(self, obj):
        return (obj.text[:75] + '...') if len(obj.text) > 75 else obj.text
    text_preview.short_description = 'Text'