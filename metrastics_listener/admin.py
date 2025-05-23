from django.contrib import admin
from .models import (
    Node,
    Packet,
    Message,
    Position,
    Telemetry,
    AverageMetricsHistory,
    Traceroute,
    ScheduledTask,
    AutoReplyRule
)

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = (
        'node_id', 'node_num', 'long_name', 'short_name', 'hw_model',
        'firmware_version', 'role', 'is_local', 'last_heard', 'battery_level',
        'snr', 'rssi', 'latitude', 'longitude', 'updated_at'
    )
    search_fields = ('node_id', 'long_name', 'short_name', 'macaddr', 'hw_model')
    list_filter = ('hw_model', 'role', 'is_local', 'firmware_version')
    readonly_fields = ('created_at', 'updated_at', 'last_heard', 'position_time', 'telemetry_time')
    fieldsets = (
        (None, {
            'fields': ('node_id', 'node_num', 'long_name', 'short_name', 'macaddr', 'hw_model', 'firmware_version', 'role', 'is_local')
        }),
        ('Status & Metrics', {
            'fields': ('last_heard', 'battery_level', 'voltage', 'channel_utilization', 'air_util_tx', 'uptime_seconds', 'snr', 'rssi')
        }),
        ('Position', {
            'fields': ('latitude', 'longitude', 'altitude', 'position_time')
        }),
        ('Timestamps & Raw Data', {
            'classes': ('collapse',),
            'fields': ('telemetry_time', 'user_info', 'position_info', 'device_metrics_info', 'environment_metrics_info', 'module_config_info', 'channel_info', 'created_at', 'updated_at')
        }),
    )

@admin.register(Packet)
class PacketAdmin(admin.ModelAdmin):
    list_display = (
        'event_id', 'timestamp', 'from_node_id_str', 'to_node_id_str',
        'packet_type', 'portnum', 'channel', 'rx_snr', 'rx_rssi', 'created_at'
    )
    search_fields = ('event_id', 'from_node_id_str', 'to_node_id_str', 'portnum', 'packet_type')
    list_filter = ('packet_type', 'portnum', 'channel', 'want_ack')
    readonly_fields = ('created_at', 'timestamp')
    raw_id_fields = ('from_node', 'to_node') # For better performance with foreign keys

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'packet_id', 'timestamp', 'from_node_id_str', 'to_node_id_str', 'text_summary',
        'channel', 'rx_snr', 'rx_rssi', 'created_at'
    )
    search_fields = ('packet__event_id', 'from_node_id_str', 'to_node_id_str', 'text')
    list_filter = ('channel',)
    readonly_fields = ('created_at', 'timestamp')
    raw_id_fields = ('packet', 'from_node', 'to_node')

    def text_summary(self, obj):
        return (obj.text[:75] + '...') if len(obj.text) > 75 else obj.text
    text_summary.short_description = 'Text'

    def packet_id(self,obj):
        return obj.packet.event_id
    packet_id.short_description = "Packet Event ID"


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        'node_link', 'timestamp', 'latitude', 'longitude', 'altitude',
        'ground_speed', 'sats_in_view', 'created_at'
    )
    search_fields = ('node__node_id', 'node__long_name')
    list_filter = ('sats_in_view',)
    readonly_fields = ('created_at', 'timestamp')
    raw_id_fields = ('node',)

    def node_link(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        if obj.node:
            link = reverse("admin:metrastics_listener_node_change", args=[obj.node.pk])
            return format_html('<a href="{}">{}</a>', link, obj.node)
        return "N/A"
    node_link.short_description = 'Node'

@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = (
        'node_link', 'timestamp', 'battery_level', 'voltage', 'channel_utilization',
        'air_util_tx', 'uptime_seconds', 'temperature', 'relative_humidity',
        'barometric_pressure', 'created_at'
    )
    search_fields = ('node__node_id', 'node__long_name')
    list_filter = ('battery_level', 'temperature', 'relative_humidity')
    readonly_fields = ('created_at', 'timestamp')
    raw_id_fields = ('node',)

    def node_link(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        if obj.node:
            link = reverse("admin:metrastics_listener_node_change", args=[obj.node.pk])
            return format_html('<a href="{}">{}</a>', link, obj.node)
        return "N/A"
    node_link.short_description = 'Node'


@admin.register(AverageMetricsHistory)
class AverageMetricsHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp', 'average_snr', 'average_rssi', 'average_battery',
        'average_chan_util', 'active_node_count', 'total_node_count', 'created_at'
    )
    readonly_fields = ('created_at', 'timestamp')

@admin.register(Traceroute)
class TracerouteAdmin(admin.ModelAdmin):
    list_display = (
        'packet_event_id', 'timestamp', 'requester_node_id_str', 'responder_node_id_str', 'created_at'
    )
    search_fields = ('packet_event_id', 'requester_node_id_str', 'responder_node_id_str')
    readonly_fields = ('created_at', 'timestamp')
    raw_id_fields = ('packet', 'requester_node', 'responder_node')

@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    list_display = ('id','nodeId', 'taskType', 'cronString', 'enabled', 'createdAt', 'updatedAt')
    search_fields = ('nodeId', 'taskType')
    list_filter = ('taskType', 'enabled')
    readonly_fields = ('createdAt', 'updatedAt')

@admin.register(AutoReplyRule)
class AutoReplyRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'trigger_phrase_summary', 'match_type', 'response_summary', 'cooldown_seconds', 'is_enabled', 'updated_at')
    search_fields = ('trigger_phrase', 'response_message')
    list_filter = ('match_type', 'is_enabled')
    readonly_fields = ('created_at', 'updated_at')

    def trigger_phrase_summary(self, obj):
        return (obj.trigger_phrase[:75] + '...') if len(obj.trigger_phrase) > 75 else obj.trigger_phrase
    trigger_phrase_summary.short_description = 'Trigger Phrase'

    def response_summary(self, obj):
        return (obj.response_message[:75] + '...') if len(obj.response_message) > 75 else obj.response_message
    response_summary.short_description = 'Response Message'