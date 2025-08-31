# metrastics_listener/management/commands/listen_device.py
import asyncio
import json
import logging
import time
import base64
import sys
import re
from typing import Optional, Any, Tuple
from datetime import datetime, timezone as dt_timezone
import threading

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction, close_old_connections, OperationalError
from django.utils import timezone as django_timezone

import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
from flask import Flask, request as flask_request, jsonify
from flask_cors import CORS # Import CORS
import requests
import openai

from metrastics_listener.models import Node, Packet, Message, Position, Telemetry, ListenerState, Traceroute
from metrastics_commander.models import CommanderRule, CommanderSettings

logger = logging.getLogger(__name__)
commander_logger = logging.getLogger('metrastics_commander')

flask_app = Flask(__name__)
# Apply CORS to the Flask app.
# For development, you can allow all origins with origins="*"
# For production, you might want to restrict it to your Django app's origin, e.g., "http://127.0.0.1:8000"
CORS(flask_app)
# Alternatively, for more specific origin control:
# CORS(flask_app, resources={r"/send_meshtastic_message": {"origins": "http://127.0.0.1:8000"}})


meshtastic_interface_instance_for_flask = None


def ensure_serializable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ensure_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [ensure_serializable(item) for item in obj]
    elif isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return f"base64:{base64.b64encode(obj).decode('utf-8')}"
    elif hasattr(obj, 'DESCRIPTOR') and hasattr(obj.DESCRIPTOR, 'fields') and not isinstance(obj, type):
        serializable_dict = {}
        for field_descriptor in obj.DESCRIPTOR.fields:
            field_name = field_descriptor.name
            try:
                value = getattr(obj, field_name)
                if isinstance(value, bytes) and field_name in ['macaddr', 'id', 'channel_id']:
                    serializable_dict[field_name] = value.hex()
                elif isinstance(value, bytes) and field_name == 'psk':
                    serializable_dict[field_name] = f"bytes_len:{len(value)}"
                elif hasattr(value, 'DESCRIPTOR') and hasattr(value.DESCRIPTOR, 'fields'):
                    serializable_dict[field_name] = ensure_serializable(value)
                else:
                    serializable_dict[field_name] = ensure_serializable(value)
            except Exception as e:
                logger.debug(f"Could not serialize Protobuf field '{field_name}': {e}")
        return serializable_dict
    try:
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError):
        logger.warning(
            f"Object of type {type(obj)} could not be serialized to dict/JSON, falling back to string representation.")
        return str(obj)


def classify_packet_type(packet_dict: dict) -> Tuple[str, Any]:
    decoded = packet_dict.get('decoded')
    if not isinstance(decoded, dict):
        if 'encrypted' in packet_dict: return "Encrypted", packet_dict.get('encrypted')
        payload = packet_dict.get('payload')
        if isinstance(payload, bytes):
            try:
                text = payload.decode('utf-8')
                if len(text) > 0 and all(32 <= ord(c) <= 126 or c in '\r\n\t ' for c in text):
                    if not isinstance(packet_dict.get('decoded'), dict): packet_dict[
                        'decoded'] = {}
                    packet_dict['decoded']['portnum'] = 'TEXT_MESSAGE_APP'
                    packet_dict['decoded']['payload'] = text
                    return "Message", text
            except UnicodeDecodeError:
                logger.debug("Payload could not be decoded as UTF-8.")
        return "Unknown", None

    portnum = decoded.get('portnum', 'UNKNOWN')
    portnum_str = getattr(portnum, 'name', str(portnum))

    if portnum_str == 'TEXT_MESSAGE_APP':
        payload = decoded.get('payload')
        if isinstance(payload, bytes):
            try:
                payload = payload.decode('utf-8')
            except UnicodeDecodeError:
                payload = f"base64:{base64.b64encode(payload).decode('utf-8')}"
        return "Message", str(payload) if payload is not None else ""
    elif portnum_str == 'POSITION_APP' and 'position' in decoded:
        return "Position", decoded['position']
    elif portnum_str == 'NODEINFO_APP' and 'user' in decoded:
        return "User Info", decoded['user']
    elif portnum_str == 'TELEMETRY_APP' and 'telemetry' in decoded:
        return "Telemetry", decoded['telemetry']
    elif portnum_str == 'ROUTING_APP':
        return "Routing", decoded.get('routing')

    if 'position' in decoded: return "Position", decoded['position']
    if 'telemetry' in decoded: return "Telemetry", decoded['telemetry']
    if 'user' in decoded: return "User Info", decoded['user']

    payload = decoded.get('payload')
    if payload is not None:
        if isinstance(payload, str): return "Message", payload
        if isinstance(payload, bytes):
            try:
                text = payload.decode('utf-8')
                if len(text) > 0 and sum(32 <= ord(c) <= 126 or c in '\r\n\t ' for c in text) / len(text) > 0.8:
                    return "Message", text
                else:
                    return "Binary Data", f"base64:{base64.b64encode(payload).decode('utf-8')}"
            except UnicodeDecodeError:
                return "Binary Data", f"base64:{base64.b64encode(payload).decode('utf-8')}"
    return "Other", decoded


def get_node_id_str(node_num_int: int) -> Optional[str]:
    if isinstance(node_num_int, int):
        return f"!{node_num_int:08x}"
    return None


def get_node_num_from_id_str(node_id_str: str) -> Optional[int]:
    if isinstance(node_id_str, str) and node_id_str.startswith('!') and len(node_id_str) > 1:
        try:
            return int(node_id_str[1:], 16)
        except ValueError:
            logger.warning(f"Could not parse node number from ID '{node_id_str}'")
    return None


_local_node_channel_map_cache = {}
_local_node_info_cache = {}


def map_internal_channel_to_user_index(internal_channel_id):
    global _local_node_channel_map_cache
    user_index = _local_node_channel_map_cache.get(internal_channel_id)
    if user_index is None:
        logger.warning(
            f"No user index for internal channel ID '{internal_channel_id}' in channel_map found. Defaulting to 0.")
        return 0
    return user_index


def format_timestamp_for_template(timestamp_epoch, default_val="N/A"):
    if timestamp_epoch is None or timestamp_epoch == 0:
        return default_val
    try:
        ts = float(timestamp_epoch)
        dt_aware = django_timezone.make_aware(datetime.fromtimestamp(ts, dt_timezone.utc))
        return django_timezone.localtime(dt_aware).strftime('%d.%m.%Y %H:%M:%S')
    except (OverflowError, OSError, ValueError, TypeError):
        logger.warning(f"Could not format timestamp: {timestamp_epoch}",
                       exc_info=False)
        return default_val


@flask_app.route('/send_meshtastic_message', methods=['POST', 'OPTIONS']) # Add OPTIONS method
def handle_send_meshtastic_message():
    # For OPTIONS requests, Flask-CORS will handle it automatically if configured.
    # You might not even need to check request.method == 'OPTIONS' explicitly.
    if flask_request.method == 'OPTIONS':
        # Flask-CORS should handle this, but if not, you can return a 200 OK.
        # The important part is that Flask-CORS adds the headers.
        return jsonify({"status": "success", "message": "CORS preflight successful"}), 200

    global meshtastic_interface_instance_for_flask
    if not meshtastic_interface_instance_for_flask:
        logger.error("Flask: Meshtastic interface not available.")
        return jsonify({"status": "error", "message": "Meshtastic interface not ready"}), 503

    try:
        data = flask_request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        text_to_send = data.get('text')
        destination_id = data.get('destinationId')
        want_ack = data.get('wantAck', True)
        channel_index = data.get('channelIndex')

        if not text_to_send or not destination_id:
            return jsonify({"status": "error", "message": "Missing 'text' or 'destinationId'"}), 400

        commander_logger.info(
            f"Flask: Received send request for {destination_id}: '{text_to_send}' (Ack: {want_ack}, Ch: {channel_index})")

        send_args = {
            "text": text_to_send,
            "destinationId": destination_id,
            "wantAck": want_ack
        }
        if channel_index is not None:
            try:
                send_args["channelIndex"] = int(channel_index)
            except ValueError:
                commander_logger.warning(f"Flask: Invalid channelIndex '{channel_index}' received, ignoring.")

        meshtastic_interface_instance_for_flask.sendText(**send_args)
        commander_logger.info(f"Flask: Message for {destination_id} passed to Meshtastic interface.")
        return jsonify({"status": "success", "message": "Message sent to Meshtastic interface"}), 200

    except meshtastic.MeshtasticException as me:
        commander_logger.error(f"Flask: MeshtasticException during sendText: {me}")
        return jsonify({"status": "error", "message": f"Meshtastic error: {str(me)}"}), 500
    except Exception as e:
        commander_logger.exception("Flask: Unexpected error in /send_meshtastic_message")
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500


def call_chatgpt_api(user_query: str) -> Optional[str]:
    api_key = settings.OPENAI_API_KEY
    system_prompt = settings.CHATGPT_SYSTEM_PROMPT

    if not api_key or api_key == "your_openai_api_key_here":
        commander_logger.error("OpenAI API key is not configured or is placeholder in settings.py.")
        return "OpenAI API key not configured."
    if not api_key.startswith("sk-"):
        commander_logger.warning(f"OpenAI API key in settings.py does not look like a valid key: {api_key[:10]}...")

    try:
        client = openai.OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            max_tokens=150
        )
        response_text = completion.choices[0].message.content
        commander_logger.info(f"ChatGPT API response: {response_text}")
        return response_text.strip()
    except openai.APIConnectionError as e:
        commander_logger.error(f"OpenAI API Connection Error: {e}")
        return "Error: Could not connect to OpenAI."
    except openai.RateLimitError as e:
        commander_logger.error(f"OpenAI API Rate Limit Error: {e}")
        return "Error: OpenAI rate limit exceeded."
    except openai.APIStatusError as e:
        commander_logger.error(f"OpenAI API Status Error (code {e.status_code}): {e.response}")
        return f"Error: OpenAI API error ({e.status_code})."
    except Exception as e:
        commander_logger.exception("Unexpected error calling OpenAI API.")
        return "Error: An unexpected error occurred with ChatGPT."


def process_commander_rules(incoming_message_obj: Message, from_node_obj: Node, flask_send_url: str,
                            original_channel_index: Optional[int]):
    global _local_node_info_cache
    if not incoming_message_obj or not from_node_obj:
        return

    message_text = incoming_message_obj.text
    sender_node_id = from_node_obj.node_id
    now_utc = datetime.now(dt_timezone.utc)
    now_iso = now_utc.isoformat()

    chatgpt_trigger = settings.CHATGPT_TRIGGER_COMMAND
    chatbot_mode_enabled = CommanderSettings.get_solo().chatbot_mode_enabled
    trigger_matched = message_text.lower().startswith(chatgpt_trigger.lower())
    if chatbot_mode_enabled or trigger_matched:
        if chatbot_mode_enabled and trigger_matched:
            user_query = message_text[len(chatgpt_trigger):].strip()
        elif chatbot_mode_enabled:
            user_query = message_text.strip()
        else:
            user_query = message_text[len(chatgpt_trigger):].strip()
        if user_query:
            commander_logger.info(
                f"ChatGPT command '{chatgpt_trigger}' triggered by {sender_node_id} with query: '{user_query}'" if trigger_matched else f"Chatbot mode enabled: forwarding message from {sender_node_id}")
            chatgpt_response = call_chatgpt_api(user_query)
            if chatgpt_response:
                max_len = 220
                if len(chatgpt_response) > max_len:
                    chatgpt_response = chatgpt_response[:max_len - 3] + "..."
                    commander_logger.warning(f"ChatGPT response for {sender_node_id} was truncated.")

                send_payload = {
                    "text": chatgpt_response,
                    "destinationId": sender_node_id,
                    "wantAck": True,
                    "channelIndex": original_channel_index
                }
                try:
                    response = requests.post(flask_send_url, json=send_payload, timeout=15)
                    response.raise_for_status()
                    commander_logger.info(
                        f"Commander: ChatGPT response for {sender_node_id} requested via HTTP. Response: {response.json()}")
                except requests.exceptions.RequestException as http_e:
                    commander_logger.error(
                        f"Commander: HTTP Error sending ChatGPT reply for {sender_node_id}: {http_e}")
                except Exception as e:
                    commander_logger.exception(
                        f"Commander: Error processing ChatGPT send request for {sender_node_id}: {e}")
            else:
                commander_logger.warning(
                    f"Commander: No response from ChatGPT for query: '{user_query}' from {sender_node_id}")
        else:
            commander_logger.info(
                f"ChatGPT command '{chatgpt_trigger}' triggered by {sender_node_id} but no query provided.")
            send_payload = {
                "text": f"Please provide a query after {chatgpt_trigger}.",
                "destinationId": sender_node_id,
                "wantAck": True,
                "channelIndex": original_channel_index
            }
            try:
                requests.post(flask_send_url, json=send_payload, timeout=10)
            except Exception:
                pass
        return

    try:
        with transaction.atomic():
            rules_list = list(CommanderRule.objects.filter(enabled=True))

            for rule in rules_list:
                if rule.cooldown_seconds > 0:
                    last_triggered_iso = rule.last_triggered_for_nodes.get(sender_node_id)
                    if last_triggered_iso:
                        try:
                            last_triggered_dt = datetime.fromisoformat(last_triggered_iso)
                            if (now_utc - last_triggered_dt).total_seconds() < rule.cooldown_seconds:
                                commander_logger.debug(
                                    f"Rule '{rule.name}' for {sender_node_id} is in cooldown. Skipping.")
                                continue
                        except ValueError:
                            commander_logger.warning(
                                f"Invalid ISO timestamp for rule '{rule.name}', node '{sender_node_id}'.")

                match = False
                trigger = rule.trigger_phrase
                if rule.match_type == 'exact':
                    match = (message_text == trigger)
                elif rule.match_type == 'contains':
                    match = (trigger.lower() in message_text.lower())
                elif rule.match_type == 'startswith':
                    match = message_text.lower().startswith(trigger.lower())
                elif rule.match_type == 'regex':
                    try:
                        if re.search(trigger, message_text, re.IGNORECASE):
                            match = True
                    except re.error as e:
                        commander_logger.error(f"Regex error in rule '{rule.name}': {e}. Skipping.")
                        continue

                if not match:
                    continue

                commander_logger.info(f"Rule '{rule.name}' triggered by '{message_text[:50]}...' from {sender_node_id}")

                response_text = rule.response_template
                replacements = {
                    "<SENDER_ID>": str(from_node_obj.node_id or "N/A"),
                    "<SENDER_NUM>": str(from_node_obj.node_num or "N/A"),
                    "<SENDER_LONG_NAME>": str(from_node_obj.long_name or "N/A"),
                    "<SENDER_SHORT_NAME>": str(from_node_obj.short_name or "N/A"),
                    "<SENDER_HW_MODEL>": str(from_node_obj.hw_model or "N/A"),
                    "<SENDER_ROLE>": str(from_node_obj.role or "N/A"),
                    "<SENDER_IS_LOCAL>": "Ja" if from_node_obj.is_local else "Nein",
                    "<SENDER_LAST_HEARD>": format_timestamp_for_template(from_node_obj.last_heard),
                    "<SENDER_SNR>": str(from_node_obj.snr or "N/A"),
                    "<SENDER_RSSI>": str(from_node_obj.rssi or "N/A"),
                    "<SENDER_LATITUDE>": str(from_node_obj.latitude or "N/A"),
                    "<SENDER_LONGITUDE>": str(from_node_obj.longitude or "N/A"),
                    "<SENDER_ALTITUDE>": str(from_node_obj.altitude or "N/A"),
                    "<SENDER_POSITION_TIME>": format_timestamp_for_template(from_node_obj.position_time),
                    "<SENDER_BATTERY_LEVEL>": str(
                        from_node_obj.battery_level if from_node_obj.battery_level not in [None, 255] else "N/A") + (
                                                  "%" if from_node_obj.battery_level not in [None, 255] else ""),
                    "<SENDER_VOLTAGE>": f"{from_node_obj.voltage:.2f}V" if from_node_obj.voltage is not None else "N/A",
                    "<SENDER_UPTIME_SECONDS>": str(from_node_obj.uptime_seconds or "N/A"),
                    "<RECEIVED_MESSAGE_TEXT>": str(incoming_message_obj.text or ""),
                    "<RECEIVED_MESSAGE_CHANNEL_INDEX>": str(
                        original_channel_index if original_channel_index is not None else "N/A"),
                    "<RECEIVED_MESSAGE_TIMESTAMP>": str(
                        int(incoming_message_obj.timestamp)) if incoming_message_obj.timestamp else "N/A",
                    "<LOCAL_NODE_ID>": str(_local_node_info_cache.get('id', "N/A")),
                    "<LOCAL_NODE_NUM>": str(_local_node_info_cache.get('num', "N/A")),
                    "<LOCAL_NODE_NAME>": str(_local_node_info_cache.get('name', "N/A")),
                    "<CURRENT_TIME_ISO>": now_iso,
                    "<CURRENT_TIME_UTC_HHMMSS>": now_utc.strftime('%H:%M:%S'),
                }
                if from_node_obj.latitude is not None and from_node_obj.longitude is not None:
                    replacements[
                        "<LOCATION>"] = f"Lat: {from_node_obj.latitude:.4f}, Lon: {from_node_obj.longitude:.4f}"
                    if from_node_obj.altitude is not None:
                        replacements["<LOCATION>"] += f", Alt: {from_node_obj.altitude}m"
                else:
                    replacements["<LOCATION>"] = "Position unbekannt"

                for placeholder, value in replacements.items():
                    response_text = response_text.replace(placeholder, value)

                max_len = 220
                if len(response_text) > max_len:
                    response_text = response_text[:max_len - 3] + "..."
                    commander_logger.warning(f"Response for rule '{rule.name}' was truncated.")

                send_payload = {
                    "text": response_text,
                    "destinationId": sender_node_id,
                    "wantAck": True,
                    "channelIndex": original_channel_index
                }
                try:
                    commander_logger.info(f"Commander: Sending POST to {flask_send_url} with payload: {send_payload}")
                    response_http = requests.post(flask_send_url, json=send_payload,
                                                  timeout=10)
                    response_http.raise_for_status()

                    commander_logger.info(
                        f"Commander: Reply for rule '{rule.name}' to {sender_node_id} requested via HTTP. Response: {response_http.json()}")

                    if response_http.json().get("status") == "success":
                        if rule.cooldown_seconds > 0:
                            if not isinstance(rule.last_triggered_for_nodes, dict):
                                rule.last_triggered_for_nodes = {}
                            rule.last_triggered_for_nodes[sender_node_id] = now_iso
                            rule.save(update_fields=['last_triggered_for_nodes', 'updated_at'])
                            commander_logger.info(
                                f"Commander: Cooldown updated for rule '{rule.name}' for node {sender_node_id}.")
                    else:
                        commander_logger.warning(
                            f"Commander: Send request via HTTP for rule '{rule.name}' reported failure: {response_http.json().get('message')}")

                except requests.exceptions.RequestException as http_e:
                    commander_logger.error(f"Commander: HTTP Error sending reply for rule '{rule.name}': {http_e}")
                except Exception as e:
                    commander_logger.exception(
                        f"Commander: Error processing send request or saving rule '{rule.name}': {e}")
                break
    except Exception as e:
        commander_logger.exception(f"Database or other critical error in process_commander_rules: {e}")


def on_receive_django(packet, interface):
    logger.debug(f"on_receive_django: Packet received: {packet}")
    try:
        close_old_connections()
        packet_data_dict = ensure_serializable(packet)

        current_time_epoch = time.time()
        packet_data_dict['timestamp'] = packet_data_dict.get('rxTime', current_time_epoch)

        packet_id_val = packet_data_dict.get('id', packet_data_dict.get('decoded', {}).get('id', 'no_id'))
        if isinstance(packet_id_val, bytes):
            packet_id_val = packet_id_val.hex()

        if 'event_id' not in packet_data_dict or not packet_data_dict['event_id']:
            packet_data_dict['event_id'] = f"pkt_{int(current_time_epoch * 1e6)}_{packet_id_val}"

        from_num = packet_data_dict.get('from')
        to_num = packet_data_dict.get('to')

        from_id_str = get_node_id_str(from_num) if from_num is not None else None
        to_id_str = None
        if to_num is not None:
            to_id_str = "^all" if to_num == 0xFFFFFFFF else get_node_id_str(to_num)

        packet_data_dict['fromId'] = from_id_str
        packet_data_dict['toId'] = to_id_str

        original_internal_channel_id = packet_data_dict.get('channel')
        if isinstance(original_internal_channel_id, bytes):
            original_internal_channel_id = original_internal_channel_id.hex()

        mapped_channel_index = map_internal_channel_to_user_index(
            original_internal_channel_id) if original_internal_channel_id is not None else 0

        app_packet_type, payload_specific_data = classify_packet_type(packet_data_dict)
        flask_send_url = f"http://localhost:{Command.FLASK_PORT}/send_meshtastic_message"

        db_packet_data = {
            'event_id': packet_data_dict['event_id'],
            'timestamp': packet_data_dict['timestamp'],
            'rx_time': packet_data_dict.get('rxTime'),
            'from_node_id_str': from_id_str,
            'to_node_id_str': to_id_str,
            'channel': mapped_channel_index,
            'portnum': getattr(packet_data_dict.get('decoded', {}).get('portnum'), 'name',
                               str(packet_data_dict.get('decoded', {}).get('portnum'))),
            'packet_type': app_packet_type,
            'rx_snr': packet_data_dict.get('rxSnr'),
            'rx_rssi': packet_data_dict.get('rxRssi'),
            'hop_limit': packet_data_dict.get('hopLimit'),
            'want_ack': packet_data_dict.get('wantAck', False),
            'decoded_json': packet_data_dict.get('decoded'),
            'raw_json': packet_data_dict,
        }

        from_node_obj = None
        to_node_obj = None

        with transaction.atomic():
            if from_id_str:
                from_node_obj, _ = Node.objects.update_or_create(
                    node_id=from_id_str,
                    defaults={
                        'node_num': from_num,
                        'last_heard': db_packet_data['timestamp'],
                        'snr': db_packet_data.get('rx_snr'),
                        'rssi': db_packet_data.get('rx_rssi'),
                    }
                )
                db_packet_data['from_node'] = from_node_obj

            if to_id_str and to_id_str != "^all":
                to_node_obj, _ = Node.objects.get_or_create(
                    node_id=to_id_str,
                    defaults={'node_num': get_node_num_from_id_str(to_id_str)}
                )
                db_packet_data['to_node'] = to_node_obj

            packet_obj = Packet.objects.create(**db_packet_data)
            logger.info(
                f"Packet {packet_obj.event_id} ({app_packet_type}) from {from_id_str or 'N/A'} to {to_id_str or 'N/A'} saved.")

            message_obj_for_commander = None

            if app_packet_type == "Message" and payload_specific_data and from_node_obj:
                message_obj_for_commander = Message.objects.create(
                    packet=packet_obj,
                    from_node=from_node_obj,
                    from_node_id_str=from_id_str,
                    to_node=to_node_obj,
                    to_node_id_str=to_id_str,
                    channel=original_internal_channel_id, # Store the raw internal channel ID hex string
                    text=str(payload_specific_data),
                    timestamp=packet_obj.timestamp,
                    rx_snr=packet_obj.rx_snr,
                    rx_rssi=packet_obj.rx_rssi
                )
                if message_obj_for_commander:
                    process_commander_rules(message_obj_for_commander, from_node_obj, flask_send_url,
                                            mapped_channel_index) # Pass the mapped user-facing channel index


            elif app_packet_type == "Position" and payload_specific_data and from_node_obj:
                pos_data = payload_specific_data
                lat = pos_data.get('latitudeI', 0) / 1e7 if pos_data.get('latitudeI') is not None else pos_data.get(
                    'latitude')
                lon = pos_data.get('longitudeI', 0) / 1e7 if pos_data.get('longitudeI') is not None else pos_data.get(
                    'longitude')
                altitude = pos_data.get('altitude')
                precision_bits = pos_data.get('precisionBits', pos_data.get('gpsPrecision'))
                ground_speed = pos_data.get('groundSpeed')
                ground_track = pos_data.get('groundTrack')
                sats_in_view = pos_data.get('satsInView')
                position_packet_time = pos_data.get('time', packet_obj.timestamp)

                if lat is not None and lon is not None:
                    Position.objects.create(
                        node=from_node_obj,
                        timestamp=position_packet_time,
                        latitude=lat,
                        longitude=lon,
                        altitude=altitude,
                        precision_bits=precision_bits,
                        ground_speed=ground_speed,
                        ground_track=ground_track,
                        sats_in_view=sats_in_view,
                        pdop=pos_data.get('pdop'),
                        hdop=pos_data.get('hdop'),
                        vdop=pos_data.get('vdop'),
                    )
                    from_node_obj.latitude = lat
                    from_node_obj.longitude = lon
                    from_node_obj.altitude = altitude
                    from_node_obj.position_time = position_packet_time
                    from_node_obj.position_info = pos_data
                    from_node_obj.save(
                        update_fields=['latitude', 'longitude', 'altitude', 'position_time', 'position_info',
                                       'updated_at'])

            elif app_packet_type == "Telemetry" and payload_specific_data and from_node_obj:
                metrics_data = payload_specific_data
                dev_metrics = metrics_data.get('deviceMetrics', {})
                env_metrics = metrics_data.get('environmentMetrics', {})
                power_metrics = metrics_data.get('powerMetrics', {})

                telemetry_packet_time = dev_metrics.get('time', power_metrics.get('time', packet_obj.timestamp))

                Telemetry.objects.create(
                    node=from_node_obj,
                    timestamp=telemetry_packet_time,
                    battery_level=dev_metrics.get('batteryLevel', power_metrics.get('batteryLevel')),
                    voltage=dev_metrics.get('voltage', power_metrics.get('voltage')),
                    channel_utilization=dev_metrics.get('channelUtilization'),
                    air_util_tx=dev_metrics.get('airUtilTx'),
                    uptime_seconds=dev_metrics.get('uptimeSeconds'),
                    temperature=env_metrics.get('temperature'),
                    relative_humidity=env_metrics.get('relativeHumidity'),
                    barometric_pressure=env_metrics.get('barometricPressure'),
                    gas_resistance=env_metrics.get('gasResistance'),
                    iaq=env_metrics.get('iaq')
                )

                current_battery = dev_metrics.get('batteryLevel', power_metrics.get('batteryLevel'))
                current_voltage = dev_metrics.get('voltage', power_metrics.get('voltage'))
                current_uptime = dev_metrics.get('uptimeSeconds')

                if current_battery is not None: from_node_obj.battery_level = current_battery
                if current_voltage is not None: from_node_obj.voltage = current_voltage
                if current_uptime is not None: from_node_obj.uptime_seconds = current_uptime
                if dev_metrics.get('channelUtilization') is not None:
                    from_node_obj.channel_utilization = dev_metrics.get('channelUtilization')
                if dev_metrics.get('airUtilTx') is not None:
                    from_node_obj.air_util_tx = dev_metrics.get('airUtilTx')

                from_node_obj.telemetry_time = telemetry_packet_time
                from_node_obj.device_metrics_info = dev_metrics
                from_node_obj.environment_metrics_info = env_metrics
                if power_metrics:
                    if not from_node_obj.device_metrics_info: from_node_obj.device_metrics_info = {}
                    from_node_obj.device_metrics_info['powerMetrics'] = power_metrics

                from_node_obj.save(update_fields=['battery_level', 'voltage', 'uptime_seconds', 'telemetry_time',
                                                  'channel_utilization', 'air_util_tx',
                                                  'device_metrics_info', 'environment_metrics_info', 'updated_at'])


            elif app_packet_type == "User Info" and payload_specific_data and from_node_obj:
                user_data = payload_specific_data
                from_node_obj.long_name = user_data.get('longName')
                from_node_obj.short_name = user_data.get('shortName')
                mac_addr_raw = user_data.get('macaddr')
                if isinstance(mac_addr_raw, bytes):
                    from_node_obj.macaddr = mac_addr_raw.hex(':')
                elif isinstance(mac_addr_raw, str):
                    from_node_obj.macaddr = mac_addr_raw

                hw_model_val = user_data.get('hwModel')
                if isinstance(hw_model_val, str) and hw_model_val != "UNSET":
                    from_node_obj.hw_model = hw_model_val
                elif hasattr(hw_model_val, 'name') and hw_model_val.name != "UNSET":
                    from_node_obj.hw_model = hw_model_val.name

                role_val = user_data.get('role')
                from_node_obj.role = getattr(role_val, 'name', str(role_val)) if role_val is not None else None
                from_node_obj.user_info = user_data
                from_node_obj.save(
                    update_fields=['long_name', 'short_name', 'macaddr', 'hw_model', 'role', 'user_info', 'updated_at'])

            elif app_packet_type == "Routing" and payload_specific_data and to_node_obj and from_node_obj:
                if not isinstance(payload_specific_data, dict):
                    logger.debug(
                        f"Routing packet payload_specific_data is not a dictionary. From: {from_id_str}, To: {to_id_str}. Data: {payload_specific_data}")
                else:
                    error_source_dict = payload_specific_data
                    route_list_source_dict = payload_specific_data

                    if 'routeDiscovery' in payload_specific_data and isinstance(payload_specific_data['routeDiscovery'],
                                                                                dict):
                        error_source_dict = payload_specific_data['routeDiscovery']
                        route_list_source_dict = payload_specific_data['routeDiscovery']
                    elif 'raw' in payload_specific_data and isinstance(payload_specific_data['raw'], dict):
                        raw_data = payload_specific_data['raw']
                        if 'route_reply' in raw_data and isinstance(raw_data['route_reply'], dict):
                            route_list_source_dict = raw_data['route_reply']
                        elif 'route_request' in raw_data and isinstance(raw_data['route_request'], dict):
                            route_list_source_dict = raw_data['route_request']

                    route_path = None
                    if 'route' in route_list_source_dict:
                        route_path_value = route_list_source_dict['route']
                        if isinstance(route_path_value, str):
                            try:
                                parsed_route = json.loads(route_path_value)
                                if isinstance(parsed_route, list):
                                    route_path = parsed_route
                                else:
                                    logger.warning(
                                        f"Parsed route from string is not a list: '{parsed_route}' for packet {packet_obj.event_id}")
                            except json.JSONDecodeError:
                                logger.warning(
                                    f"Could not parse route string as JSON: '{route_path_value}' for packet {packet_obj.event_id}")
                        elif isinstance(route_path_value, list):
                            route_path = route_path_value
                        else:
                            logger.warning(
                                f"Unexpected type for 'route' value: {type(route_path_value)} for packet {packet_obj.event_id}")

                    actual_error_reason_str = None
                    if 'errorReason' in error_source_dict:
                        error_val = error_source_dict['errorReason']
                        actual_error_reason_str = getattr(error_val, 'name', str(error_val)).upper()
                    elif 'error_reason' in error_source_dict:
                        error_val = error_source_dict['error_reason']
                        if isinstance(error_val, int) and error_val == 0:
                            actual_error_reason_str = "NONE"
                        else:
                            actual_error_reason_str = getattr(error_val, 'name', str(error_val)).upper()

                    is_significant_error = actual_error_reason_str is not None and \
                                           actual_error_reason_str not in ["NONE", "NO_ERROR"]

                    if route_path is not None and isinstance(route_path, list) and not is_significant_error:
                        logger.info(
                            f"Traceroute processed. Requester: {to_id_str}, Responder: {from_id_str}. Path: {route_path}. Reported error status: {actual_error_reason_str or 'Not present'}")
                        Traceroute.objects.create(
                            packet=packet_obj,
                            packet_event_id=packet_obj.event_id,
                            requester_node=to_node_obj,
                            requester_node_id_str=to_id_str,
                            responder_node=from_node_obj,
                            responder_node_id_str=from_id_str,
                            route_json=route_path,
                            timestamp=packet_obj.timestamp
                        )
                    elif is_significant_error:
                        logger.info(
                            f"Significant routing error reported. Requester: {to_id_str}, Responder: {from_id_str}. Error: {actual_error_reason_str}. Full routing data: {payload_specific_data}")
                    else:
                        logger.debug(
                            f"Routing packet from {from_id_str} to {to_id_str} did not yield a usable route list and no significant error. payload_specific_data: {payload_specific_data}")


    except Exception as e:
        logger.exception(f"Error in on_receive_django: {e}")


def on_node_updated_django(node, interface):
    logger.debug(f"on_node_updated_django: Node data received: {node} (Type: {type(node)})")
    if not isinstance(node, dict) and not hasattr(node, '__dict__'):
        logger.warning(
            f"on_node_updated_django: Unexpected type for node: {type(node)} with value: {repr(node)}. Expecting dict or object with attributes. Ignoring event."
        )
        return

    try:
        close_old_connections()
        node_data_dict = ensure_serializable(node)

        if not isinstance(node_data_dict, dict):
            logger.warning(
                f"on_node_updated_django: After serialization, node_data_dict is not a dict! Type: {type(node_data_dict)} with value: {repr(node_data_dict)}. Ignoring event."
            )
            return

        node_num = node_data_dict.get('num')
        if node_num is None:
            node_num = node_data_dict.get('myNodeNum')

        if node_num is None:
            logger.warning("Node update without 'num' or 'myNodeNum' received, ignoring.")
            return

        node_id_str = get_node_id_str(node_num)
        if not node_id_str:
            logger.error(f"Could not generate a valid node ID for number {node_num}.")
            return

        user_payload = node_data_dict.get('user', {}) if isinstance(node_data_dict.get('user'), dict) else {}
        pos_payload = node_data_dict.get('position', {}) if isinstance(node_data_dict.get('position'), dict) else {}
        dev_metrics_payload = node_data_dict.get('deviceMetrics', {}) if isinstance(node_data_dict.get('deviceMetrics'),
                                                                                    dict) else {}
        power_metrics_payload = node_data_dict.get('powerMetrics', dev_metrics_payload.get('powerMetrics', {})) \
            if isinstance(node_data_dict.get('powerMetrics', dev_metrics_payload.get('powerMetrics')), dict) else {}
        env_metrics_payload = node_data_dict.get('environmentMetrics', {}) if isinstance(
            node_data_dict.get('environmentMetrics'), dict) else {}

        defaults_to_update = {
            'node_num': node_num,
            'long_name': user_payload.get('longName', node_data_dict.get('longName')),
            'short_name': user_payload.get('shortName', node_data_dict.get('shortName')),
            'macaddr': user_payload.get('macaddr'),
            'hw_model': user_payload.get('hwModel') or node_data_dict.get('hwModelStr') or node_data_dict.get(
                'hwVersion') or node_data_dict.get('pioEnv'),
            'firmware_version': node_data_dict.get('firmwareVersion') or node_data_dict.get('swVersion'),
            'role': getattr(user_payload.get('role'), 'name',
                            str(user_payload.get('role', node_data_dict.get('role')))),
            'is_local': node_data_dict.get('isLocal', False),
            'last_heard': node_data_dict.get('lastHeard', time.time()),
            'battery_level': dev_metrics_payload.get('batteryLevel', power_metrics_payload.get('batteryLevel')),
            'voltage': dev_metrics_payload.get('voltage', power_metrics_payload.get('voltage')),
            'channel_utilization': dev_metrics_payload.get('channelUtilization'),
            'air_util_tx': dev_metrics_payload.get('airUtilTx'),
            'uptime_seconds': dev_metrics_payload.get('uptimeSeconds'),
            'snr': node_data_dict.get('snr'),
            'rssi': node_data_dict.get('hopRssi', node_data_dict.get('rssi')),
            'latitude': (pos_payload.get('latitudeI', 0) / 1e7) if pos_payload.get(
                'latitudeI') is not None else pos_payload.get('latitude'),
            'longitude': (pos_payload.get('longitudeI', 0) / 1e7) if pos_payload.get(
                'longitudeI') is not None else pos_payload.get('longitude'),
            'altitude': pos_payload.get('altitude'),
            'position_time': pos_payload.get('time'),
            'telemetry_time': dev_metrics_payload.get('time', power_metrics_payload.get('time')),
            'user_info': user_payload or None,
            'position_info': pos_payload or None,
            'device_metrics_info': dev_metrics_payload or None,
            'environment_metrics_info': env_metrics_payload or None,
            'module_config_info': node_data_dict.get('moduleConfig', node_data_dict.get('modulePrefs')),
            'channel_info': node_data_dict.get('channelSettings', node_data_dict.get('channels')),
        }
        if hasattr(defaults_to_update['hw_model'], 'name'):
            defaults_to_update['hw_model'] = defaults_to_update['hw_model'].name

        if power_metrics_payload and (
                not defaults_to_update['device_metrics_info'] or defaults_to_update['device_metrics_info'].get(
                'powerMetrics') != power_metrics_payload):
            if not defaults_to_update['device_metrics_info']: defaults_to_update['device_metrics_info'] = {}
            defaults_to_update['device_metrics_info']['powerMetricsFromNodeUpdate'] = power_metrics_payload

        update_values = {k: v for k, v in defaults_to_update.items() if v is not None}

        with transaction.atomic():
            node_obj, created = Node.objects.update_or_create(
                node_id=node_id_str,
                defaults=update_values
            )
        log_action = "created" if created else "updated"
        logger.info(f"Node {node_obj.node_id} ({node_obj.long_name or node_obj.short_name or 'N/A'}) {log_action}.")

    except Exception as e:
        node_identifier = node_data_dict.get('num', 'UNKNOWN') if isinstance(node_data_dict, dict) else (
            node.get('num', 'UNKNOWN_NODE') if isinstance(node, dict) else 'UNKNOWN_TYPE')
        logger.exception(f"Error in on_node_updated_django for node {node_identifier}: {e}")


def on_connection_django(interface, topic=pub.AUTO_TOPIC, reason=None):
    global _local_node_channel_map_cache, _local_node_info_cache
    topic_str = getattr(topic, 'getNamePath', lambda: str(topic))()
    logger.info(f"on_connection_django: Connection event: {topic_str}" + (f" Reason: {reason}" if reason else ""))
    close_old_connections()

    status_update = {'updated_at': django_timezone.now()}
    new_status = ListenerState.STATUS_CHOICES[5][0]
    current_error_msg_for_state = reason

    if "meshtastic.connection.established" in topic_str:
        new_status = ListenerState.STATUS_CHOICES[2][0]
        status_update['last_error_message'] = None
        current_error_msg_for_state = None
        logger.info("Meshtastic connection established.")
        try:
            if interface and hasattr(interface, 'myInfo') and interface.myInfo:
                my_info_raw_obj = interface.myInfo
                my_info_dict = ensure_serializable(my_info_raw_obj)

                if not isinstance(my_info_dict, dict):
                    error_detail = f"Processed myInfo is not a dictionary (type: {type(my_info_dict)}, value: '{str(my_info_dict)[:200]}...'). Cannot extract local node details."
                    logger.error(error_detail)
                    status_update['last_error_message'] = error_detail
                    current_error_msg_for_state = error_detail
                    _local_node_info_cache.clear()
                else:
                    local_node_num_int = my_info_dict.get('myNodeNum')
                    local_node_id_str = get_node_id_str(local_node_num_int) if local_node_num_int is not None else None

                    user_info_from_myinfo = my_info_dict.get('user', {}) if isinstance(my_info_dict.get('user'),
                                                                                       dict) else {}
                    local_node_name_str = my_info_dict.get('longName') or \
                                          user_info_from_myinfo.get('longName') or \
                                          my_info_dict.get('shortName') or \
                                          user_info_from_myinfo.get('shortName')

                    if not local_node_name_str and local_node_num_int is not None:
                        local_node_name_str = f"Node {local_node_num_int}"
                    elif not local_node_name_str:
                        local_node_name_str = f"Local Node ({local_node_id_str or 'Unknown ID'})"

                    status_update.update({
                        'local_node_id': local_node_id_str,
                        'local_node_num': local_node_num_int,
                        'local_node_name': local_node_name_str,
                    })
                    _local_node_info_cache = {'id': local_node_id_str, 'num': local_node_num_int,
                                              'name': local_node_name_str}
                    commander_logger.info(f"Local node cache updated: {_local_node_info_cache}")

                    current_channel_map = {}
                    if hasattr(interface, 'localNode') and interface.localNode and hasattr(interface.localNode,
                                                                                           'channels'):
                        if isinstance(interface.localNode.channels, list):
                            for ch_protobuf in interface.localNode.channels:
                                if hasattr(ch_protobuf, 'index') and hasattr(ch_protobuf, 'settings') and \
                                        hasattr(ch_protobuf.settings, 'id'):
                                    internal_channel_id_bytes = ch_protobuf.settings.id
                                    if isinstance(internal_channel_id_bytes, bytes):
                                        internal_channel_id_hex = internal_channel_id_bytes.hex()
                                        current_channel_map[internal_channel_id_hex] = ch_protobuf.index
                                    else:
                                        logger.warning(
                                            f"Channel settings ID is not bytes: {internal_channel_id_bytes}, type: {type(internal_channel_id_bytes)}")
                                        current_channel_map[str(internal_channel_id_bytes)] = ch_protobuf.index
                                else:
                                    logger.warning(
                                        f"A channel object in localNode.channels is missing expected attributes. Channel: {ch_protobuf}")
                        else:
                            logger.warning(
                                f"interface.localNode.channels is not a list. Type: {type(interface.localNode.channels)}")
                    else:
                        logger.warning(
                            "Could not get channel map: interface.localNode or interface.localNode.channels is missing or not as expected.")

                    _local_node_channel_map_cache = current_channel_map
                    status_update['local_node_channel_map_json'] = current_channel_map
                    logger.info(
                        f"Local node info: ID {local_node_id_str}, Name: {local_node_name_str}. Channel Map: {current_channel_map}")

                    on_node_updated_django(my_info_raw_obj, interface)
            else:
                logger.warning("myInfo not available from interface on connection established.")
                _local_node_info_cache.clear()
                status_update['last_error_message'] = "myInfo not available from interface."
                current_error_msg_for_state = status_update['last_error_message']


        except AttributeError as ae:
            logger.exception(f"AttributeError while processing myInfo: {ae}")
            current_error_msg_for_state = status_update[
                'last_error_message'] = f"Error processing local node info (AttributeError): {str(ae)}"
            _local_node_info_cache.clear()
        except Exception as e:
            logger.exception(f"General error processing myInfo on connection established: {e}")
            current_error_msg_for_state = status_update[
                'last_error_message'] = f"Error processing local node info: {str(e)}"
            _local_node_info_cache.clear()

    elif "meshtastic.connection.lost" in topic_str:
        new_status = ListenerState.STATUS_CHOICES[3][0]
        current_error_msg_for_state = current_error_msg_for_state or "Connection lost"
        logger.warning(f"Meshtastic connection lost. Reason: {current_error_msg_for_state}")
        _local_node_channel_map_cache.clear()
        _local_node_info_cache.clear()
        status_update.update({
            'local_node_channel_map_json': {},
            'local_node_id': None, 'local_node_num': None, 'local_node_name': None
        })

    elif "meshtastic.connection.failed" in topic_str:
        new_status = ListenerState.STATUS_CHOICES[4][0]
        current_error_msg_for_state = current_error_msg_for_state or "Connection attempt failed (event)"
        logger.error(f"Meshtastic connection attempt failed. Reason: {current_error_msg_for_state}")
        _local_node_channel_map_cache.clear()
        _local_node_info_cache.clear()
        status_update.update({
            'local_node_channel_map_json': {},
            'local_node_id': None, 'local_node_num': None, 'local_node_name': None
        })

    status_update['status'] = new_status
    if 'last_error_message' not in status_update and current_error_msg_for_state:
        status_update['last_error_message'] = current_error_msg_for_state

    with transaction.atomic():
        ListenerState.objects.update_or_create(singleton_id=1, defaults=status_update)

    final_error_message_for_log = status_update.get('last_error_message')
    logger.info(f"Listener status in DB: {new_status}" + (
        f" (Error: {final_error_message_for_log})" if final_error_message_for_log else ""))


class Command(BaseCommand):
    help = 'Starts the Meshtastic Listener to collect data and provide a send API.'
    _meshtastic_interface = None
    FLASK_PORT = 5555 # This is the hardcoded port for the Flask app

    def run_flask_app(self):
        global meshtastic_interface_instance_for_flask
        meshtastic_interface_instance_for_flask = self._meshtastic_interface

        flask_log = logging.getLogger('werkzeug')
        flask_log.setLevel(logging.ERROR) # Keep Flask's own logging quiet
        # flask_app.logger.disabled = True # This might be too aggressive; werkzeug logger is better

        logger.info(f"Starting Flask API server on host 0.0.0.0, port {self.FLASK_PORT} in a separate thread...")
        try:
            # Use the FLASK_PORT from settings if available, otherwise default
            actual_flask_port = getattr(settings, 'LISTENER_FLASK_PORT', self.FLASK_PORT)
            if isinstance(actual_flask_port, str): actual_flask_port = int(actual_flask_port)

            if actual_flask_port != self.FLASK_PORT: # Update class default if setting is different for consistency
                logger.info(f"Overriding hardcoded FLASK_PORT ({self.FLASK_PORT}) with LISTENER_FLASK_PORT from settings: {actual_flask_port}")
                Command.FLASK_PORT = actual_flask_port # Update for flask_send_url in on_receive_django

            flask_app.run(host='0.0.0.0', port=actual_flask_port, threaded=True, use_reloader=False, debug=False)
        except Exception as e:
            logger.exception(f"Flask API server failed to start or crashed: {e}")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Meshtastic Listener with Send API..."))
        logger.info("Meshtastic Listener Management Command started.")

        # Update Command.FLASK_PORT from Django settings if available
        # This makes the flask_send_url in on_receive_django use the configured port
        try:
            configured_flask_port = getattr(settings, 'LISTENER_FLASK_PORT', str(Command.FLASK_PORT))
            Command.FLASK_PORT = int(configured_flask_port)
            logger.info(f"Flask app within listener will run on port {Command.FLASK_PORT} (from settings or default).")
        except ValueError:
            logger.error(f"Invalid LISTENER_FLASK_PORT value in settings: {settings.LISTENER_FLASK_PORT}. Using default {Command.FLASK_PORT}.")
            Command.FLASK_PORT = 5555 # Fallback to original hardcoded default

        flask_api_thread = None
        flask_thread_started_successfully = False

        close_old_connections()
        with transaction.atomic():
            ListenerState.objects.update_or_create(
                singleton_id=1,
                defaults={'status': ListenerState.STATUS_CHOICES[0][0], 'updated_at': django_timezone.now()}
            )

        host = settings.MESHTASTIC_DEVICE_HOST
        port = settings.MESHTASTIC_DEVICE_PORT
        retry_delay = 5
        max_retry_delay = 60

        pub.subscribe(on_receive_django, "meshtastic.receive")
        pub.subscribe(on_node_updated_django, "meshtastic.node.updated")
        pub.subscribe(on_connection_django, "meshtastic.connection.established")
        pub.subscribe(on_connection_django, "meshtastic.connection.lost")
        pub.subscribe(on_connection_django, "meshtastic.connection.failed")

        while True:
            close_old_connections()

            try:
                current_listener_state = ListenerState.objects.get(singleton_id=1)
                if current_listener_state.restart_requested:
                    logger.info("Restart request detected for the listener.")
                    if self._meshtastic_interface:
                        try:
                            logger.info("Closing existing Meshtastic interface for restart...")
                            self._meshtastic_interface.close()
                        except Exception as e_close:
                            logger.error(f"Error closing Meshtastic interface during restart: {e_close}")
                    self._meshtastic_interface = None
                    meshtastic_interface_instance_for_flask = None
                    flask_thread_started_successfully = False

                    with transaction.atomic():
                        ListenerState.objects.filter(singleton_id=1).update(
                            status=ListenerState.STATUS_CHOICES[0][0],
                            restart_requested=False,
                            last_error_message="Listener restart initiated by user.",
                            updated_at=django_timezone.now()
                        )
                    logger.info("Listener restart initiated. Will attempt to reconnect.")
                    retry_delay = 1
            except ListenerState.DoesNotExist:
                logger.warning("ListenerState not found in database. Cannot check for restart request.")
            except OperationalError as oe_db:
                logger.error(f"Database error when checking for restart request: {oe_db}. Retrying DB operation later.")
                time.sleep(retry_delay)
                continue
            except Exception as e_restart_check:
                logger.exception(f"Unexpected error checking for listener restart: {e_restart_check}")

            if self._meshtastic_interface is None:
                logger.info(f"Attempting to connect to Meshtastic: {host}:{port}")
                with transaction.atomic():
                    ListenerState.objects.update_or_create(
                        singleton_id=1,
                        defaults={'status': ListenerState.STATUS_CHOICES[1][0], 'last_error_message': None,
                                  'updated_at': django_timezone.now()}
                    )
                try:
                    self._meshtastic_interface = meshtastic.tcp_interface.TCPInterface(
                        hostname=host,
                        portNumber=port,
                        noProto=False,
                    )
                    meshtastic_interface_instance_for_flask = self._meshtastic_interface

                    logger.info(f"TCPInterface object created for {host}:{port}. Waiting for connection events.")

                    if not flask_api_thread or not flask_api_thread.is_alive():
                        logger.info("Meshtastic interface object (re)created. (Re)starting Flask API thread.")
                        flask_api_thread = threading.Thread(target=self.run_flask_app, daemon=True)
                        flask_api_thread.start()
                        time.sleep(2)
                        if flask_api_thread.is_alive():
                            logger.info("Flask API thread seems to be running.")
                            flask_thread_started_successfully = True
                        else:
                            logger.error("Flask API thread did not start correctly!")
                            flask_thread_started_successfully = False
                    retry_delay = 5

                except ConnectionRefusedError as e:
                    err_msg = f"Connection to {host}:{port} refused. Detail: {e}"
                    logger.error(err_msg)
                    pub.sendMessage("meshtastic.connection.failed", interface=None, reason=err_msg)
                    self._meshtastic_interface = None
                except meshtastic.MeshtasticException as e:
                    err_msg = f"Meshtastic library error: {e}"
                    logger.error(err_msg)
                    pub.sendMessage("meshtastic.connection.failed", interface=None, reason=err_msg)
                    self._meshtastic_interface = None
                except Exception as e:
                    err_msg = f"Unexpected error during connection attempt: {e}"
                    logger.exception(err_msg)
                    pub.sendMessage("meshtastic.connection.failed", interface=None, reason=err_msg)
                    self._meshtastic_interface = None

                if self._meshtastic_interface is None:
                    logger.info(f"Connection attempt failed. Waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    flask_thread_started_successfully = False
                    continue

            if self._meshtastic_interface:
                try:
                    if flask_thread_started_successfully and (not flask_api_thread or not flask_api_thread.is_alive()):
                        logger.warning(
                            "Flask API thread is no longer alive! Closing Meshtastic interface to trigger reconnect and Flask restart.")
                        if self._meshtastic_interface:
                            try:
                                self._meshtastic_interface.close()
                            except:
                                pass
                        self._meshtastic_interface = None
                        flask_thread_started_successfully = False
                        continue

                    if not (hasattr(self._meshtastic_interface,
                                    'socket') and self._meshtastic_interface.socket is not None):
                        logger.warning(
                            "Meshtastic interface socket is None (periodic check). Connection might be lost.")
                        if self._meshtastic_interface:
                            try:
                                self._meshtastic_interface.close()
                            except Exception as close_err:
                                logger.error(f"Error during defensive close of interface: {close_err}")
                        self._meshtastic_interface = None
                        flask_thread_started_successfully = False
                        continue

                    time.sleep(5)

                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING(" Meshtastic Listener stopping..."))
                    if self._meshtastic_interface:
                        self._meshtastic_interface.close()
                    close_old_connections()
                    with transaction.atomic():
                        ListenerState.objects.update_or_create(singleton_id=1, defaults={
                            'status': ListenerState.STATUS_CHOICES[3][0],
                            'last_error_message': "Listener shut down by user.",
                            'restart_requested': False,
                            'updated_at': django_timezone.now()
                        })
                    break
                except Exception as e:
                    logger.exception(f"Unexpected error in main listener operational loop: {e}")
                    if self._meshtastic_interface:
                        try:
                            self._meshtastic_interface.close()
                        except:
                            pass
                    self._meshtastic_interface = None
                    flask_thread_started_successfully = False
                    with transaction.atomic():
                        ListenerState.objects.update_or_create(singleton_id=1, defaults={
                            'status': ListenerState.STATUS_CHOICES[4][0],
                            'last_error_message': f"Main loop error: {str(e)}",
                            'restart_requested': False,
                            'updated_at': django_timezone.now()
                        })
                    time.sleep(retry_delay)
            else:
                time.sleep(retry_delay)