# mqtt_listener/management/commands/listen_mqtt.py
import paho.mqtt.client as mqtt
import json
import time
import hashlib  # Für den Hash
from datetime import datetime, timezone as dt_timezone  # Wichtig für Django Timezones
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction  # Für atomare Datenbankoperationen
from django.db.models import Q  # Hinzugefügt für die erweiterte Node-Suche

# Modelle importieren
from mqtt_listener.models import Node, MessagePacket, Position, Telemetry, TextMessage

# Mapping-Konstanten
# Diese Listen sollten so vollständig wie möglich sein.
# Quelle: Meshtastic-Dokumentation / Quellcode (z.B. protobuf Definitionen)
HW_MODELS = {
    0: "UNSET",
    1: "TLORA_V2",
    2: "TLORA_V1",
    3: "TLORA_V2_1_1P6",
    4: "TBEAM",
    5: "HELTEC_V2_1",
    6: "TBEAM_M8N_OLD",
    7: "HELTEC_V2_0",
    8: "HELTEC_V1_OLD",
    9: "LILYGO_TBEAM_S3_CORE",
    10: "RAK4631",
    11: "HELTEC_V3",
    12: "ESP32_S3_DEV",
    13: "LILYGO_T3S3",
    14: "LILYGO_T_ECHO",
    15: "NAMING_C",
    16: "PICOMPUTER",
    17: "STATION_G1",
    18: "NRF52840_PCA10059",
    19: "LILYGO_LORA32_V2_1",
    20: "RP_PICO_W_LORA",
    33: "RAK11200",
    34: "RAK11300",
    35: "NRF52_DK",
    36: "WIPHONE",
    37: "CANARY_ONE",
    38: "BETAFPV_ELRS_MICRO_TX_MODULE_V2",
    39: "RADIOMASTER_ZORRO_ELRS",
    40: "FRIENDLYWRT_NANOPI_NEO3_LORA",
    41: "SENSECAP_INDICATOR_D1S",
    254: "PRIVATE_HW",
    255: "UNKNOWN"
}

ROLES = {
    0: "CLIENT",
    1: "CLIENT_MUTE",
    2: "ROUTER",
    3: "ROUTER_CLIENT",
    4: "REPEATER",
    5: "TAK_CLIENT",
}


def decimal_degrees(degrees_i):
    if degrees_i is None:
        return None
    return degrees_i / 1e7


def get_or_create_node_from_id(node_id_any_format, long_name=None, short_name=None, hw_model_int=None, role_int=None):
    """
    Sucht oder erstellt einen Node anhand seiner ID (Dezimal oder Hex '!...').
    Aktualisiert optional Node-Informationen und stellt sicher, dass beide ID-Formate (dez/hex) gespeichert werden.
    """
    node = None
    created = False
    # Diese Variablen speichern die aus node_id_any_format extrahierten Werte
    parsed_node_id_dec = None
    parsed_node_id_hex = None

    if isinstance(node_id_any_format, str) and node_id_any_format.startswith('!'):
        parsed_node_id_hex = node_id_any_format
        try:
            parsed_node_id_dec = int(parsed_node_id_hex.lstrip('!'), 16)
        except ValueError:
            # Ungültige Hex-ID, sollte nicht passieren, wenn Format '!...' ist
            return None, False
    elif isinstance(node_id_any_format, int):
        parsed_node_id_dec = node_id_any_format
        parsed_node_id_hex = f"!{parsed_node_id_dec:08x}"
    else:
        # Ungültiges Format für node_id_any_format
        return None, False

    # Versuche, den Node anhand einer der beiden ID-Formen zu finden
    # Priorisiere die Hex-ID, falls vorhanden, da sie oft als "primärer" angesehen wird
    if parsed_node_id_hex:
        try:
            node = Node.objects.get(Q(node_id_hex=parsed_node_id_hex) | Q(node_id_dec=parsed_node_id_dec))
        except Node.DoesNotExist:
            pass  # Node wird später erstellt
        except Node.MultipleObjectsReturned:  # Falls die DB inkonsistent ist (sollte nicht sein bei unique constraints)
            node = Node.objects.filter(Q(node_id_hex=parsed_node_id_hex) | Q(node_id_dec=parsed_node_id_dec)).first()
    elif parsed_node_id_dec is not None:  # Fallback, wenn nur Dezimal-ID (z.B. wenn Konvertierung von Hex fehlschlug, aber Dezimal-Int übergeben wurde)
        try:
            node = Node.objects.get(node_id_dec=parsed_node_id_dec)
        except Node.DoesNotExist:
            pass
        except Node.MultipleObjectsReturned:
            node = Node.objects.filter(node_id_dec=parsed_node_id_dec).first()

    # Node erstellen, falls nicht gefunden
    if not node:
        if parsed_node_id_hex:  # Primär mit Hex erstellen, wenn vorhanden
            node, created = Node.objects.get_or_create(
                node_id_hex=parsed_node_id_hex,
                defaults={'node_id_dec': parsed_node_id_dec}  # Dezimal-ID direkt mitgeben
            )
        elif parsed_node_id_dec is not None:  # Ansonsten mit Dezimal erstellen
            node, created = Node.objects.get_or_create(
                node_id_dec=parsed_node_id_dec,
                defaults={'node_id_hex': parsed_node_id_hex}  # Hex-ID direkt mitgeben
            )
        else:
            # Sollte nicht erreicht werden, wenn die obige Logik node_id_any_format korrekt verarbeitet
            return None, False

    updated_fields = {}

    if created:
        print(
            f"  >> Node CREATED for input: {node_id_any_format} -> DB Node ID {node.pk}, Hex: {node.node_id_hex}, Dec: {node.node_id_dec}")
        # Beim Erstellen wurden die IDs bereits durch 'defaults' gesetzt oder durch das Suchfeld in get_or_create.
        # Eine explizite Zuweisung hier ist meist nicht mehr nötig, außer zur Korrektur von Inkonsistenzen.

    if node:
        # Node-Informationen aktualisieren (Name, Hardware, Rolle)
        if long_name and node.long_name != long_name:
            node.long_name = long_name
            updated_fields['long_name'] = True
        if short_name and node.short_name != short_name:
            node.short_name = short_name
            updated_fields['short_name'] = True
        if hw_model_int is not None:
            hw_str = HW_MODELS.get(hw_model_int, f"Unbekannt ({hw_model_int})")
            if node.hardware_model_str != hw_str:
                node.hardware_model_str = hw_str
                updated_fields['hardware_model_str'] = True
        if role_int is not None:
            role_str = ROLES.get(role_int, f"Unbekannt ({role_int})")
            if node.role_str != role_str:
                node.role_str = role_str
                updated_fields['role_str'] = True

        # Sicherstellen, dass beide ID-Formate im Node-Objekt konsistent sind
        # basierend auf den geparsten Werten vom Input
        if parsed_node_id_dec is not None and node.node_id_dec != parsed_node_id_dec:
            node.node_id_dec = parsed_node_id_dec
            updated_fields['node_id_dec'] = True
        elif parsed_node_id_dec is not None and not node.node_id_dec:  # Falls es vorher fehlte
            node.node_id_dec = parsed_node_id_dec
            updated_fields['node_id_dec'] = True

        if parsed_node_id_hex and node.node_id_hex != parsed_node_id_hex:
            node.node_id_hex = parsed_node_id_hex
            updated_fields['node_id_hex'] = True
        elif parsed_node_id_hex and not node.node_id_hex:  # Falls es vorher fehlte
            node.node_id_hex = parsed_node_id_hex
            updated_fields['node_id_hex'] = True

        # Fallback: Wenn eine ID-Form im Node-Objekt fehlt, aber die andere vorhanden ist,
        # leite die fehlende Form ab (dies sollte durch obige Logik eigentlich schon erledigt sein)
        if node.node_id_dec is not None and not node.node_id_hex:
            derived_hex = f"!{int(node.node_id_dec):08x}"
            if node.node_id_hex != derived_hex:
                node.node_id_hex = derived_hex
                updated_fields['node_id_hex'] = True
        elif node.node_id_hex and node.node_id_hex.startswith('!') and node.node_id_dec is None:
            try:
                derived_dec = int(node.node_id_hex.lstrip('!'), 16)
                if node.node_id_dec != derived_dec:
                    node.node_id_dec = derived_dec
                    updated_fields['node_id_dec'] = True
            except ValueError:
                print(f"  Error converting hex '{node.node_id_hex}' to decimal for node {node_id_any_format}")

        if updated_fields:
            fields_to_save = list(updated_fields.keys())
            if fields_to_save:
                node.save(update_fields=fields_to_save)
                display_id = node.long_name or node.node_id_hex or str(node.node_id_dec)
                print(f"  >> Node UPDATED: {display_id} (Input: {node_id_any_format}) with {fields_to_save}")
    return node, created


class Command(BaseCommand):
    help = 'Starts the MQTT listener to receive and process Meshtastic data.'

    def handle(self, *args, **options):
        client_id = f"django-meshtastic-listener-{int(time.time())}"
        if hasattr(mqtt, 'CallbackAPIVersion') and mqtt.CallbackAPIVersion.VERSION1 == mqtt.CallbackAPIVersion.VERSION1:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
        else:
            client = mqtt.Client(client_id=client_id)

        if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        def on_connect(client, userdata, flags, reason_code, properties=None):
            if reason_code == 0:
                self.stdout.write(self.style.SUCCESS(f"Successfully connected to MQTT Broker {settings.MQTT_BROKER}."))
                client.subscribe(settings.MQTT_TOPIC)
                self.stdout.write(f"Subscribed to topic: {settings.MQTT_TOPIC}")
            else:
                self.stderr.write(f"Connection failed with code: {reason_code}")

        def on_message(client, userdata, msg):
            try:
                payload_str = msg.payload.decode('utf-8')
                packet_hash = hashlib.sha256(msg.payload).hexdigest()

                if MessagePacket.objects.filter(packet_hash=packet_hash).exists():
                    self.stdout.write(f"  -- Duplicate packet ignored (Hash: {packet_hash[:8]}...)")
                    return

                data = json.loads(payload_str)
                timestamp_mqtt_utc = datetime.fromtimestamp(data.get("timestamp", time.time()), tz=dt_timezone.utc)
                self.stdout.write(
                    f"\n--- New message at {timestamp_mqtt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} on Topic: {msg.topic} ---")

                topic_parts = msg.topic.split('/')
                channel_id_val = None
                gateway_id_hex_val = None

                if len(topic_parts) > 3 and topic_parts[3] == 'json' and topic_parts[1] != '':
                    try:
                        channel_id_val = int(topic_parts[2])
                    except ValueError:
                        self.stdout.write(f"  Could not parse channel_id from topic part: {topic_parts[2]}")
                    if len(topic_parts) > 4 and topic_parts[4].startswith('!'):
                        gateway_id_hex_val = topic_parts[4]

                from_node_id_dec = data.get("from")
                sender_node_id_hex = data.get("sender")

                from_node_obj, _ = get_or_create_node_from_id(from_node_id_dec)
                sender_node_obj = None
                if sender_node_id_hex:
                    # Sender kann auch eine Dezimalzahl sein, die als String kommt (selten bei 'sender')
                    # Für '!...' ist es klar hex.
                    # Wichtig: get_or_create_node_from_id verarbeitet Hex-Strings und Ints.
                    sender_node_obj, _ = get_or_create_node_from_id(sender_node_id_hex)

                with transaction.atomic():
                    packet_log = MessagePacket.objects.create(
                        packet_hash=packet_hash,
                        timestamp_mqtt=timestamp_mqtt_utc,
                        topic=msg.topic,
                        from_node=from_node_obj,
                        to_node_id_dec=data.get("to"),
                        sender_node=sender_node_obj if sender_node_obj != from_node_obj else None,
                        channel_id=channel_id_val,
                        gateway_id_hex=gateway_id_hex_val,
                        rssi_mqtt=data.get("rssi"),
                        snr_mqtt=data.get("snr"),
                        hops_away_mqtt=data.get("hops_away"),
                        hop_limit=data.get("hop_limit"),
                        hop_start=data.get("hop_start"),
                        message_type=data.get("type"),
                        raw_json_payload=data
                    )
                    self.stdout.write(f"  Saved: MessagePacket ID {packet_log.id}")

                    payload = data.get("payload")
                    msg_type = data.get("type")

                    if payload:
                        node_for_data = from_node_obj  # Standardmäßig dem 'from_node' zuordnen

                        if msg_type == "position" and node_for_data:
                            lat = decimal_degrees(payload.get("latitude_i"))
                            lon = decimal_degrees(payload.get("longitude_i"))
                            alt = payload.get("altitude")
                            pdop_val = payload.get("PDOP")
                            if isinstance(pdop_val, int): pdop_val = pdop_val / 100.0

                            ts_device_unix = payload.get("time")
                            ts_device_utc = None
                            if ts_device_unix:
                                try:
                                    ts_device_utc = datetime.fromtimestamp(ts_device_unix, tz=dt_timezone.utc)
                                except (OSError, OverflowError, TypeError,
                                        ValueError) as e:  # Fehler bei ungültigem Timestamp abfangen
                                    self.stdout.write(
                                        f"    Invalid device timestamp for position: {ts_device_unix}, error: {e}")

                            Position.objects.create(
                                packet=packet_log,
                                latitude=lat,
                                longitude=lon,
                                altitude=alt,
                                precision_bits=payload.get("precision_bits"),
                                sats_in_view=payload.get("sats_in_view"),
                                pdop=pdop_val,
                                timestamp_device=ts_device_utc
                            )
                            self.stdout.write(f"    Position data saved for {node_for_data}.")

                        elif msg_type == "telemetry" and node_for_data:
                            voltage_val = payload.get("voltage")
                            if isinstance(voltage_val, (int, float)): voltage_val /= 1000.0

                            Telemetry.objects.create(
                                packet=packet_log,
                                battery_level=payload.get("battery_level"),
                                voltage=voltage_val,
                                uptime_seconds=payload.get("uptime_seconds"),
                                air_util_tx=payload.get("air_util_tx"),
                                channel_utilization=payload.get("channel_utilization")
                            )
                            self.stdout.write(f"    Telemetry data saved for {node_for_data}.")

                        elif msg_type == "text" and node_for_data:
                            text_content = payload.get("text", payload_str if isinstance(payload,
                                                                                         str) else "Kein Textfeld gefunden")
                            TextMessage.objects.create(
                                packet=packet_log,
                                text=text_content
                            )
                            self.stdout.write(f"    Text message saved from {node_for_data}.")

                        elif msg_type == "nodeinfo":
                            # NodeInfo kann sich auf den 'from_node' oder eine ID in der Payload beziehen
                            node_id_in_payload = payload.get("id")  # Kann Dezimal oder !Hex sein
                            user_payload = payload.get("user")  # Enthält longname, shortname, etc.

                            target_node_id_for_info = node_id_in_payload or (
                                from_node_obj.node_id_dec if from_node_obj else None)

                            if target_node_id_for_info:
                                longname_val = None
                                shortname_val = None
                                hw_model_int_val = payload.get(
                                    "hardware")  # hardware ist direkt im payload, nicht in user
                                role_int_val = None  # role ist im user payload

                                if user_payload:  # Meshtastic > 2.0
                                    longname_val = user_payload.get("longName")
                                    shortname_val = user_payload.get("shortName")
                                    role_int_val = ROLES.get(user_payload.get("role"),
                                                             None)  # role als String, konvertieren in int
                                    if isinstance(user_payload.get("role"), str):  # String zu Int mappen
                                        # Invert ROLES dict for string lookup
                                        role_str_to_int = {v: k for k, v in ROLES.items()}
                                        role_int_val = role_str_to_int.get(user_payload.get("role"))

                                else:  # Ältere Meshtastic Versionen < 2.0 hatten longname etc. direkt im payload
                                    longname_val = payload.get("longname")
                                    shortname_val = payload.get("shortname")
                                    role_int_val = payload.get("role")

                                target_node_obj, _ = get_or_create_node_from_id(
                                    target_node_id_for_info,
                                    long_name=longname_val,
                                    short_name=shortname_val,
                                    hw_model_int=hw_model_int_val,
                                    role_int=role_int_val
                                )
                                if target_node_obj:
                                    self.stdout.write(f"    NodeInfo processed for {target_node_obj}.")
                                else:
                                    self.stdout.write(
                                        f"    NodeInfo received, but target node ({target_node_id_for_info}) could not be identified/created.")
                            else:
                                self.stdout.write(
                                    f"    NodeInfo received, but no target node ID found (from_node or payload.id).")


            except json.JSONDecodeError:
                self.stderr.write(f"Error parsing JSON: {msg.payload.decode('utf-8', errors='ignore')}")
            except Exception as e:
                self.stderr.write(f"An unexpected error occurred in on_message: {e}")
                import traceback
                self.stderr.write(traceback.format_exc())
                self.stderr.write(f"Raw data: {msg.payload.decode('utf-8', errors='ignore')}")

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            self.stdout.write(f"Attempting to connect to MQTT Broker {settings.MQTT_BROKER}...")
            client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
            client.loop_forever()
        except ConnectionRefusedError:
            self.stderr.write(
                f"Connection to {settings.MQTT_BROKER}:{settings.MQTT_PORT} refused. Is the server running and reachable?")
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("MQTT listener stopped by user (KeyboardInterrupt)."))
        except Exception as e:
            self.stderr.write(f"An error occurred in the main loop or connection setup: {e}")
            import traceback
            self.stderr.write(traceback.format_exc())
        finally:
            if hasattr(client, 'is_connected') and client.is_connected():  # is_connected für paho-mqtt > 1.5.x
                client.disconnect()
                client.loop_stop()  # Wichtig, um den Netzwerk-Thread sauber zu beenden
            elif not hasattr(client, 'is_connected'):  # Ältere paho-mqtt Versionen
                client.disconnect()  # Hier könnte es einen Fehler geben, wenn nicht verbunden
                client.loop_stop()

            self.stdout.write(self.style.WARNING("MQTT connection disconnected and loop stopped."))
