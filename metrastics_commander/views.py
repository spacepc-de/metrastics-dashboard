# metrastics_commander/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
import json
from .models import CommanderRule
from django.conf import settings # Import settings

# @login_required # Uncomment if login is required
def commander_page(request):
    rules = CommanderRule.objects.all()
    chatgpt_trigger_command = getattr(settings, 'CHATGPT_TRIGGER_COMMAND', '!chat')
    placeholders = [
        {"name": "<SENDER_ID>", "desc": "ID des Absenderknotens (z.B. !abcdef12)."},
        {"name": "<SENDER_NUM>", "desc": "Nummer des Absenderknotens."},
        {"name": "<SENDER_LONG_NAME>", "desc": "Langer Name des Absenders."},
        {"name": "<SENDER_SHORT_NAME>", "desc": "Kurzer Name des Absenders."},
        {"name": "<SENDER_HW_MODEL>", "desc": "Hardware-Modell des Absenders."},
        {"name": "<SENDER_LATITUDE>", "desc": "Breitengrad des Absenders."},
        {"name": "<SENDER_LONGITUDE>", "desc": "Längengrad des Absenders."},
        {"name": "<SENDER_ALTITUDE>", "desc": "Höhe des Absenders."},
        {"name": "<SENDER_POSITION_TIME>", "desc": "Zeitstempel der Position des Absenders (lesbar)."},
        {"name": "<SENDER_LAST_HEARD>", "desc": "Wann der Absender zuletzt gehört wurde (lesbar)."},
        {"name": "<SENDER_SNR>", "desc": "SNR des letzten Pakets vom Absender."},
        {"name": "<SENDER_RSSI>", "desc": "RSSI des letzten Pakets vom Absender."},
        {"name": "<SENDER_BATTERY_LEVEL>", "desc": "Batteriestand des Absenders (%)."},
        {"name": "<SENDER_VOLTAGE>", "desc": "Spannung des Absenders (V)."},
        {"name": "<RECEIVED_MESSAGE_TEXT>", "desc": "Der Text der empfangenen Nachricht."},
        {"name": "<RECEIVED_MESSAGE_TIMESTAMP>", "desc": "Unix-Zeitstempel der empfangenen Nachricht."},
        {"name": "<RECEIVED_MESSAGE_CHANNEL_INDEX>", "desc": "Kanalindex (0-7), auf dem die Nachricht empfangen wurde."},
        {"name": "<LOCAL_NODE_ID>", "desc": "ID des lokalen Knotens."},
        {"name": "<LOCAL_NODE_NUM>", "desc": "Nummer des lokalen Knotens."},
        {"name": "<LOCAL_NODE_NAME>", "desc": "Name des lokalen Knotens."},
        {"name": "<CURRENT_TIME_ISO>", "desc": "Aktuelle Zeit im ISO-Format (UTC)."},
        {"name": "<CURRENT_TIME_UTC_HHMMSS>", "desc": "Aktuelle Zeit als HH:MM:SS (UTC)."},
    ]
    context = {
        'rules': rules,
        'placeholders': placeholders,
        'match_type_choices': CommanderRule.MATCH_TYPE_CHOICES,
        'chatgpt_trigger_command': chatgpt_trigger_command,
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
            return JsonResponse({'status': 'error', 'message': 'Name darf nicht leer sein.'}, status=400)
        if rule.cooldown_seconds < 0:
            return JsonResponse({'status': 'error', 'message': 'Cooldown darf nicht negativ sein.'}, status=400)

        rule.save()
        return JsonResponse({'status': 'success', 'message': 'Regel erfolgreich aktualisiert.'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Ungültiges JSON-Format.'}, status=400)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Ungültiger Wert für Cooldown (muss eine Zahl sein).'},
                            status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ein Fehler ist aufgetreten: {str(e)}'}, status=500)


@require_POST
# @csrf_exempt # If not sending CSRF token with JS, otherwise remove. Best to send CSRF.
def api_delete_commander_rule(request, rule_id):
    rule = get_object_or_404(CommanderRule, pk=rule_id)
    try:
        rule.delete()
        return JsonResponse({'status': 'success', 'message': 'Regel erfolgreich gelöscht.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ein Fehler ist aufgetreten: {str(e)}'}, status=500)