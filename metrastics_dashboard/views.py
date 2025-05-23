# metrastics_dashboard/views.py
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.utils import timezone
from datetime import timedelta, datetime # Added datetime
import logging # Added logging
from django.forms.models import model_to_dict

# Make sure Traceroute is imported from metrastics_listener.models
from metrastics_listener.models import Node, Packet, Message, Position, Telemetry, \
    ListenerState, Traceroute # Added Traceroute
from django.db.models import Count, Avg, Q # Added Q for search query in api_get_all_nodes

logger = logging.getLogger(__name__) # Added logger instance


def dashboard(request):
    return render(request, 'metrastics_dashboard/dashboard.html')

def nodes_page(request):
    """Renders the new page that will list all nodes."""
    return render(request, 'metrastics_dashboard/nodes.html')

def map_page(request): # New view for the map page
    """Renders the new page that will display a map of all nodes."""
    return render(request, 'metrastics_dashboard/map.html')


def api_connection_status(request):
    """
    Liefert den aktuellen Verbindungsstatus des Meshtastic-Listeners aus der Datenbank.
    """
    try:
        state = ListenerState.objects.get(singleton_id=1)
        status_data = {
            "status": state.get_status_display(),
            "raw_status": state.status,
            "error": state.last_error_message,
            "local_node_info": {
                "node_id": state.local_node_id,
                "node_num": state.local_node_num,
                "name": state.local_node_name,
                "channel_map": state.local_node_channel_map_json
            },
            "updated_at": state.updated_at.isoformat() if state.updated_at else None
        }
    except ListenerState.DoesNotExist:
        status_data = {
            "status": "Unknown",
            "raw_status": "UNKNOWN",
            "error": "Listener-Status nicht in der Datenbank gefunden.",
            "local_node_info": {},
            "updated_at": None
        }
    return JsonResponse(status_data)


def api_counters(request):
    total_packets = Packet.objects.count()
    total_nodes = Node.objects.count()
    message_packets = Packet.objects.filter(packet_type='Message').count()
    position_packets = Packet.objects.filter(packet_type='Position').count()
    telemetry_packets = Packet.objects.filter(packet_type='Telemetry').count()
    userinfo_packets = Packet.objects.filter(
        packet_type__in=['User Info', 'NODEINFO_APP']).count()
    traceroute_packets_count = Traceroute.objects.count() # Changed from other_packets

    data = {
        'total_packets': total_packets,
        'total_nodes': total_nodes,
        'message_packets': message_packets,
        'position_packets': position_packets,
        'telemetry_packets': telemetry_packets,
        'userinfo_packets': userinfo_packets,
        'traceroute_packets': traceroute_packets_count, # Changed from other_packets
    }
    return JsonResponse(data)


def api_nodes(request):
    """ API endpoint for the dashboard - returns top N recently active nodes. """
    # Fetch additional fields latitude and longitude for potential map use on dashboard
    nodes = Node.objects.order_by('-last_heard').values(
        'node_id', 'node_num', 'long_name', 'short_name', 'hw_model',
        'last_heard', 'battery_level', 'snr', 'rssi', 'position_time',
        'latitude', 'longitude' # Added latitude and longitude
    )[:50]
    return JsonResponse(list(nodes), safe=False)

def api_get_all_nodes(request):
    """ API endpoint for the Nodes page and Map page - returns all nodes, can be searched/filtered by query params if needed. """
    search_query = request.GET.get('q', None)
    nodes_query = Node.objects.all()

    if search_query:
        nodes_query = nodes_query.filter(
            Q(long_name__icontains=search_query) |
            Q(short_name__icontains=search_query) |
            Q(node_id__icontains=search_query) |
            Q(hw_model__icontains=search_query)
        )

    # Ensure latitude and longitude are included for the map.
    nodes = nodes_query.order_by('-last_heard').values(
        'node_id', 'node_num', 'long_name', 'short_name', 'hw_model',
        'last_heard', 'battery_level', 'snr', 'rssi', 'position_time',
        'latitude', 'longitude' # Added latitude and longitude
    )
    return JsonResponse(list(nodes), safe=False)


def api_node_detail(request, node_id):
    """ Returns all available details for a single node. """
    try:
        node = Node.objects.get(node_id=node_id)
        node_details = model_to_dict(node)

        # Convert FloatField timestamps (Unix epoch) to ISO format strings
        for field_name in ['last_heard', 'position_time', 'telemetry_time']:
            timestamp_val = node_details.get(field_name)
            if isinstance(timestamp_val, (int, float)) and timestamp_val > 0:
                try:
                    # Create a naive datetime object from the Unix timestamp
                    dt_naive = datetime.fromtimestamp(timestamp_val)
                    # Make it timezone-aware using the project's default timezone
                    dt_aware = timezone.make_aware(dt_naive)
                    # Convert to the local timezone (defined by TIME_ZONE in settings) and format as ISO string
                    node_details[field_name] = timezone.localtime(dt_aware).isoformat()
                except (OverflowError, OSError, ValueError) as e:
                    logger.warning(f"Could not convert timestamp for field {field_name} with value {timestamp_val} for node {node_id}: {e}")
                    node_details[field_name] = None # Set to None if conversion fails
            elif timestamp_val is not None:
                node_details[field_name] = None

        # Format DateTimeFields (which are already datetime objects from model_to_dict) to ISO format strings
        for field_name in ['created_at', 'updated_at']:
            datetime_obj = node_details.get(field_name)
            if isinstance(datetime_obj, datetime):
                if timezone.is_aware(datetime_obj):
                    node_details[field_name] = timezone.localtime(datetime_obj).isoformat()
                else:
                    logger.warning(f"Naive datetime object found for field {field_name} for node {node_id}. Assuming default timezone.")
                    dt_aware = timezone.make_aware(datetime_obj)
                    node_details[field_name] = timezone.localtime(dt_aware).isoformat()
            elif datetime_obj is not None:
                 logger.warning(f"Unexpected type for field {field_name} (expected datetime) for node {node_id}: {type(datetime_obj)}. Converting to string.")
                 node_details[field_name] = str(datetime_obj)

        return JsonResponse(node_details)
    except Node.DoesNotExist:
        raise Http404("Node not found")
    except Exception as e:
        logger.error(f"Error in api_node_detail for node {node_id}: {e}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred processing node details.", "detail": str(e)}, status=500)


def api_live_packets(request):
    recent_packets = Packet.objects.order_by('-timestamp').select_related('from_node', 'to_node').values(
        'event_id', 'timestamp', 'from_node_id_str', 'to_node_id_str',
        'packet_type', 'portnum', 'channel', 'rx_snr', 'rx_rssi',
        'decoded_json'
    )[:20]

    packets_data = []
    for p in recent_packets:
        packet_data = dict(p)
        if p['from_node_id_str']:
            try:
                from_node = Node.objects.values('long_name', 'short_name', 'node_id').get(node_id=p['from_node_id_str'])
                packet_data['from_node_info'] = from_node
            except Node.DoesNotExist:
                packet_data['from_node_info'] = None
        else:
            packet_data['from_node_info'] = None

        if p['to_node_id_str'] and p['to_node_id_str'] != '^all':
            try:
                to_node = Node.objects.values('long_name', 'short_name', 'node_id').get(node_id=p['to_node_id_str'])
                packet_data['to_node_info'] = to_node
            except Node.DoesNotExist:
                packet_data['to_node_info'] = None
        else:
            packet_data['to_node_info'] = None
        packets_data.append(packet_data)

    return JsonResponse(packets_data, safe=False)


def api_average_signal_stats(request):
    """
    Calculates average SNR and RSSI for packets in the last 12 hours.
    """
    twelve_hours_ago = timezone.now() - timedelta(hours=12)
    twelve_hours_ago_ts = twelve_hours_ago.timestamp()
    relevant_packets = Packet.objects.filter(timestamp__gte=twelve_hours_ago_ts)

    aggregates = relevant_packets.aggregate(
        avg_snr=Avg('rx_snr'),
        avg_rssi=Avg('rx_rssi')
    )

    data = {
        'average_snr': aggregates['avg_snr'] if aggregates['avg_snr'] is not None else None,
        'average_rssi': aggregates['avg_rssi'] if aggregates['avg_rssi'] is not None else None,
        'period_hours': 12,
        'packet_count_for_avg': relevant_packets.count()
    }
    return JsonResponse(data)