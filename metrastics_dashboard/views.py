# metrastics_dashboard/views.py
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.utils import timezone
from datetime import timedelta, datetime
import logging
from django.forms.models import model_to_dict
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings # Import Django settings
import os # Import os for getenv, though settings is preferred

# Make sure Traceroute is imported from metrastics_listener.models
from metrastics_listener.models import Node, Packet, Message, Position, Telemetry, \
    ListenerState, Traceroute
from django.db.models import Count, Avg, Q

logger = logging.getLogger(__name__)


def dashboard(request):
    context = {'FLASK_PORT': getattr(settings, 'LISTENER_FLASK_PORT', '5555')}
    return render(request, 'metrastics_dashboard/dashboard.html', context)

def nodes_page(request):
    """Renders the new page that will list all nodes."""
    return render(request, 'metrastics_dashboard/nodes.html')

def map_page(request):
    """Renders the new page that will display a map of all nodes."""
    return render(request, 'metrastics_dashboard/map.html')

def messages_page(request):
    """Renders the page that lists all messages and allows sending."""
    context = {
        # Use Django settings to get LISTENER_FLASK_PORT
        'FLASK_PORT': getattr(settings, 'LISTENER_FLASK_PORT', '5555')
    }
    return render(request, 'metrastics_dashboard/messages.html', context)

def traceroutes_page(request):
    """Renders the page that lists all traceroutes."""
    return render(request, 'metrastics_dashboard/traceroutes.html')


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
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            "restart_requested": state.restart_requested
        }
    except ListenerState.DoesNotExist:
        status_data = {
            "status": "Unknown",
            "raw_status": "UNKNOWN",
            "error": "Listener-Status nicht in der Datenbank gefunden.",
            "local_node_info": {},
            "updated_at": None,
            "restart_requested": False
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
    traceroute_packets_count = Traceroute.objects.count()

    data = {
        'total_packets': total_packets,
        'total_nodes': total_nodes,
        'message_packets': message_packets,
        'position_packets': position_packets,
        'telemetry_packets': telemetry_packets,
        'userinfo_packets': userinfo_packets,
        'traceroute_packets': traceroute_packets_count,
    }
    return JsonResponse(data)


def api_nodes(request):
    """ API endpoint for the dashboard - returns top N recently active nodes. """
    nodes = Node.objects.order_by('-last_heard').values(
        'node_id', 'node_num', 'long_name', 'short_name', 'hw_model',
        'last_heard', 'battery_level', 'voltage', 'snr', 'rssi', 'position_time',
        'latitude', 'longitude'
    )[:50]
    return JsonResponse(list(nodes), safe=False)

def api_get_all_nodes(request):
    """ API endpoint for the Nodes page, Map page, and Message Send Recipient list - returns all nodes. """
    search_query = request.GET.get('q', None)
    nodes_query = Node.objects.all()

    if search_query:
        nodes_query = nodes_query.filter(
            Q(long_name__icontains=search_query) |
            Q(short_name__icontains=search_query) |
            Q(node_id__icontains=search_query) |
            Q(hw_model__icontains=search_query)
        )

    nodes = nodes_query.order_by('long_name', 'short_name', 'node_id').values(
        'node_id', 'node_num', 'long_name', 'short_name', 'hw_model',
        'last_heard', 'battery_level', 'voltage', 'snr', 'rssi', 'position_time',
        'latitude', 'longitude'
    )
    return JsonResponse(list(nodes), safe=False)


def api_node_detail(request, node_id):
    """ Returns all available details for a single node. """
    try:
        node = Node.objects.get(node_id=node_id)
        node_details = model_to_dict(node)

        for field_name in ['last_heard', 'position_time', 'telemetry_time']:
            timestamp_val = node_details.get(field_name)
            if isinstance(timestamp_val, (int, float)) and timestamp_val > 0:
                try:
                    dt_naive = datetime.fromtimestamp(timestamp_val)
                    dt_aware = timezone.make_aware(dt_naive)
                    node_details[field_name] = timezone.localtime(dt_aware).isoformat()
                except (OverflowError, OSError, ValueError) as e:
                    logger.warning(f"Could not convert timestamp for field {field_name} with value {timestamp_val} for node {node_id}: {e}")
                    node_details[field_name] = None
            elif timestamp_val is not None:
                node_details[field_name] = None

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


def api_request_listener_restart_view(request):
    if request.method == 'POST':
        logger.info("API request to restart listener received by dashboard view.")
        try:
            state, created = ListenerState.objects.get_or_create(singleton_id=1)
            if state.status in [ListenerState.STATUS_CHOICES[0][0], ListenerState.STATUS_CHOICES[1][0]] or state.restart_requested:
                 return JsonResponse({'status': 'warning', 'message': 'Listener is currently initializing, connecting, or a restart is already pending. Please wait.'}, status=409)

            state.restart_requested = True
            state.last_error_message = "Restart requested via API."
            state.save()
            logger.info("Listener restart flag set in database.")
            return JsonResponse({'status': 'success', 'message': 'Listener restart request successfully submitted.'})
        except Exception as e:
            logger.exception("Error setting listener restart flag in api_request_listener_restart_view.")
            return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Only POST requests allowed.'}, status=405)

def api_get_messages(request):
    page_number = request.GET.get('page', 1)
    search_query = request.GET.get('q', '')

    message_list = Message.objects.select_related('from_node', 'to_node').order_by('-timestamp')

    if search_query:
        message_list = message_list.filter(
            Q(text__icontains=search_query) |
            Q(from_node_id_str__icontains=search_query) |
            Q(to_node_id_str__icontains=search_query) |
            Q(from_node__long_name__icontains=search_query) |
            Q(from_node__short_name__icontains=search_query) |
            Q(to_node__long_name__icontains=search_query) |
            Q(to_node__short_name__icontains=search_query)
        )

    paginator = Paginator(message_list, 25)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    data = []
    for msg in page_obj.object_list:
        msg_data = {
            'id': msg.pk,
            'from_node_id_str': msg.from_node_id_str,
            'from_node_name': msg.from_node.long_name if msg.from_node else (msg.from_node.short_name if msg.from_node else msg.from_node_id_str),
            'to_node_id_str': msg.to_node_id_str,
            'to_node_name': msg.to_node.long_name if msg.to_node else (msg.to_node.short_name if msg.to_node else msg.to_node_id_str),
            'text': msg.text,
            'timestamp': msg.timestamp,
            'channel': msg.channel,
            'rx_snr': msg.rx_snr,
            'rx_rssi': msg.rx_rssi,
            'created_at': msg.created_at.isoformat(),
        }
        data.append(msg_data)

    return JsonResponse({
        'messages': data,
        'page': page_obj.number,
        'pages': paginator.num_pages,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'total_messages': paginator.count
    })


def api_get_traceroutes(request):
    page_number = request.GET.get('page', 1)
    search_query = request.GET.get('q', '')

    traceroute_list = Traceroute.objects.select_related('requester_node', 'responder_node').order_by('-timestamp')

    if search_query:
         traceroute_list = traceroute_list.filter(
            Q(requester_node_id_str__icontains=search_query) |
            Q(responder_node_id_str__icontains=search_query) |
            Q(requester_node__long_name__icontains=search_query) |
            Q(requester_node__short_name__icontains=search_query) |
            Q(responder_node__long_name__icontains=search_query) |
            Q(responder_node__short_name__icontains=search_query) |
            Q(packet_event_id__icontains=search_query)
        )

    paginator = Paginator(traceroute_list, 25)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    data = []
    for tr in page_obj.object_list:
        tr_data = {
            'id': tr.id,
            'packet_event_id': tr.packet_event_id,
            'requester_node_id_str': tr.requester_node_id_str,
            'requester_node_name': tr.requester_node.long_name if tr.requester_node else (tr.requester_node.short_name if tr.requester_node else tr.requester_node_id_str),
            'responder_node_id_str': tr.responder_node_id_str,
            'responder_node_name': tr.responder_node.long_name if tr.responder_node else (tr.responder_node.short_name if tr.responder_node else tr.responder_node_id_str),
            'route_json': tr.route_json,
            'timestamp': tr.timestamp,
            'created_at': tr.created_at.isoformat(),
        }
        data.append(tr_data)

    return JsonResponse({
        'traceroutes': data,
        'page': page_obj.number,
        'pages': paginator.num_pages,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'total_traceroutes': paginator.count
    })