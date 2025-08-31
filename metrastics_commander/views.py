# metrastics_commander/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from .models import CommanderRule, CommanderSettings
from django.conf import settings  # Import settings

# @login_required # Uncomment if login is required
def commander_page(request):
    rules = CommanderRule.objects.all()
    chatgpt_trigger_command = getattr(settings, 'CHATGPT_TRIGGER_COMMAND', '!chat')
    chatbot_mode_enabled = CommanderSettings.get_solo().chatbot_mode_enabled
    placeholders = [
        {"name": "<SENDER_ID>", "desc": "ID of the sender node (e.g., !abcdef12)."},
        {"name": "<SENDER_NUM>", "desc": "Number of the sender node."},
        {"name": "<SENDER_LONG_NAME>", "desc": "Long name of the sender."},
        {"name": "<SENDER_SHORT_NAME>", "desc": "Short name of the sender."},
        {"name": "<SENDER_HW_MODEL>", "desc": "Hardware model of the sender."},
        {"name": "<SENDER_LATITUDE>", "desc": "Latitude of the sender."},
        {"name": "<SENDER_LONGITUDE>", "desc": "Longitude of the sender."},
        {"name": "<SENDER_ALTITUDE>", "desc": "Altitude of the sender."},
        {"name": "<SENDER_POSITION_TIME>", "desc": "Timestamp of the sender's position (readable)."},
        {"name": "<SENDER_LAST_HEARD>", "desc": "When the sender was last heard (readable)."},
        {"name": "<SENDER_SNR>", "desc": "SNR of the last packet from the sender."},
        {"name": "<SENDER_RSSI>", "desc": "RSSI of the last packet from the sender."},
        {"name": "<SENDER_BATTERY_LEVEL>", "desc": "Battery level of the sender (%)."},
        {"name": "<SENDER_VOLTAGE>", "desc": "Voltage of the sender (V)."},
        {"name": "<RECEIVED_MESSAGE_TEXT>", "desc": "The text of the received message."},
        {"name": "<RECEIVED_MESSAGE_TIMESTAMP>", "desc": "Unix timestamp of the received message."},
        {"name": "<RECEIVED_MESSAGE_CHANNEL_INDEX>", "desc": "Channel index (0-7) on which the message was received."},
        {"name": "<LOCAL_NODE_ID>", "desc": "ID of the local node."},
        {"name": "<LOCAL_NODE_NUM>", "desc": "Number of the local node."},
        {"name": "<LOCAL_NODE_NAME>", "desc": "Name of the local node."},
        {"name": "<CURRENT_TIME_ISO>", "desc": "Current time in ISO format (UTC)."},
        {"name": "<CURRENT_TIME_UTC_HHMMSS>", "desc": "Current time as HH:MM:SS (UTC)."},
    ]
    context = {
        'rules': rules,
        'placeholders': placeholders,
        'match_type_choices': CommanderRule.MATCH_TYPE_CHOICES,
        'chatgpt_trigger_command': chatgpt_trigger_command,
        'chatbot_mode_enabled': chatbot_mode_enabled,
    }
    return render(request, 'metrastics_commander/commander.html', context)

# --- (api_get_commander_rules, api_commander_rule_detail, api_update_commander_rule, api_delete_commander_rule remain the same) ---
@require_GET
def api_get_commander_rules(request):
    rules = CommanderRule.objects.all().values(
        'id', 'name', 'trigger_phrase', 'match_type', 'response_template', 'enabled', 'cooldown_seconds', 'updated_at'
    )
    return JsonResponse(list(rules), safe=False)


@require_GET
def api_commander_rule_detail(request, rule_id):
    rule = get_object_or_404(CommanderRule, pk=rule_id)
    data = {
        'id': rule.id,
        'name': rule.name,
        'trigger_phrase': rule.trigger_phrase,
        'match_type': rule.match_type,
        'response_template': rule.response_template,
        'enabled': rule.enabled,
        'cooldown_seconds': rule.cooldown_seconds,
    }
    return JsonResponse(data)


@require_POST
# @csrf_exempt # If not sending CSRF token with JS, otherwise remove. Best to send CSRF.
def api_update_commander_rule(request, rule_id):
    rule = get_object_or_404(CommanderRule, pk=rule_id)
    try:
        data = json.loads(request.body)

        rule.name = data.get('name', rule.name)
        rule.trigger_phrase = data.get('trigger_phrase', rule.trigger_phrase)
        rule.match_type = data.get('match_type', rule.match_type)
        rule.response_template = data.get('response_template', rule.response_template)
        rule.enabled = data.get('enabled', rule.enabled)
        rule.cooldown_seconds = int(data.get('cooldown_seconds', rule.cooldown_seconds))

        # Basic validation example
        if not rule.name:
            return JsonResponse({'status': 'error', 'message': 'Name cannot be empty.'}, status=400)
        if rule.cooldown_seconds < 0:
            return JsonResponse({'status': 'error', 'message': 'Cooldown cannot be negative.'}, status=400)

        rule.save()
        return JsonResponse({'status': 'success', 'message': 'Rule successfully updated.'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid value for Cooldown (must be a number).'},
                            status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)


@require_POST
# @csrf_exempt # If not sending CSRF token with JS, otherwise remove. Best to send CSRF.
def api_delete_commander_rule(request, rule_id):
    rule = get_object_or_404(CommanderRule, pk=rule_id)
    try:
        rule.delete()
        return JsonResponse({'status': 'success', 'message': 'Rule successfully deleted.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)


@require_http_methods(["GET", "POST"])
def api_chatbot_mode(request):
    settings_obj = CommanderSettings.get_solo()
    if request.method == "GET":
        return JsonResponse({'enabled': settings_obj.chatbot_mode_enabled})
    try:
        data = json.loads(request.body)
        settings_obj.chatbot_mode_enabled = bool(data.get('enabled', False))
        settings_obj.save(update_fields=['chatbot_mode_enabled'])
        return JsonResponse({'status': 'success', 'enabled': settings_obj.chatbot_mode_enabled})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)