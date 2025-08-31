# metrastics_commander/admin.py
from django.contrib import admin
from .models import CommanderRule, CommanderSettings

@admin.register(CommanderRule)
class CommanderRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'trigger_phrase', 'match_type', 'response_template', 'enabled', 'cooldown_seconds', 'updated_at')
    list_filter = ('enabled', 'match_type')
    search_fields = ('name', 'trigger_phrase', 'response_template')
    fieldsets = (
        (None, {
            'fields': ('name', 'trigger_phrase', 'match_type', 'response_template', 'enabled', 'cooldown_seconds')
        }),
        ('Status (Automatisch verwaltet)', {
            'classes': ('collapse',),
            'fields': ('last_triggered_for_nodes', 'created_at', 'updated_at'),
        }),
    )
    readonly_fields = ('last_triggered_for_nodes', 'created_at', 'updated_at')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Provide help text for available placeholders
        form.base_fields['response_template'].help_text += (
            "<br><br><b>Verfügbare Platzhalter:</b><br>"
            "&lt;SENDER_ID&gt;, &lt;SENDER_NUM&gt;, &lt;SENDER_LONG_NAME&gt;, &lt;SENDER_SHORT_NAME&gt;,<br>"
            "&lt;SENDER_HW_MODEL&gt;, &lt;SENDER_ROLE&gt;, &lt;SENDER_IS_LOCAL&gt;,<br>"
            "&lt;SENDER_LAST_HEARD&gt;, &lt;SENDER_SNR&gt;, &lt;SENDER_RSSI&gt;,<br>"
            "&lt;SENDER_LATITUDE&gt;, &lt;SENDER_LONGITUDE&gt;, &lt;SENDER_ALTITUDE&gt;, &lt;SENDER_POSITION_TIME&gt;,<br>"
            "&lt;SENDER_BATTERY_LEVEL&gt;, &lt;SENDER_VOLTAGE&gt;, &lt;SENDER_UPTIME_SECONDS&gt;,<br>"
            "&lt;RECEIVED_MESSAGE_TEXT&gt;, &lt;RECEIVED_MESSAGE_TIMESTAMP&gt; (Unix Epoch), &lt;RECEIVED_MESSAGE_CHANNEL_INDEX&gt;,<br>"
            "&lt;LOCAL_NODE_ID&gt;, &lt;LOCAL_NODE_NUM&gt;, &lt;LOCAL_NODE_NAME&gt;,<br>"
            "&lt;CURRENT_TIME_ISO&gt;, &lt;CURRENT_TIME_UTC_HHMMSS&gt;"
        )
        return form


@admin.register(CommanderSettings)
class CommanderSettingsAdmin(admin.ModelAdmin):
    list_display = ('chatbot_mode_enabled',)