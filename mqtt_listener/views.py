# mqtt_listener/views.py
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Max, Subquery, OuterRef, Count, F, Case, When, Value, BooleanField
from django.db.models.functions import Coalesce
from .models import Node, MessagePacket, Position, Telemetry, TextMessage
import json
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, Http404  # Added Http404 for explicit raising
from django.views.decorators.http import require_GET
from django.shortcuts import render



@require_GET
def get_node_positions_for_map(request):
    """
    Liefert die neuesten Positionsdaten für alle Nodes, die Positionsdaten haben,
    sowie deren Status (online/offline basierend auf der letzten Aktivität).
    """
    latest_position_subquery = Position.objects.filter(
        packet__from_node=OuterRef('pk')
    ).order_by(
        F('timestamp_device').desc(nulls_last=True),  # Bevorzuge timestamp_device
        F('packet__timestamp_mqtt').desc()
    ).values('pk')[:1]

    latest_positions = Position.objects.filter(
        pk__in=Subquery(
            Node.objects.annotate(
                last_pos_id=Subquery(latest_position_subquery)
            ).filter(last_pos_id__isnull=False).values('last_pos_id')
        )
    ).select_related('packet__from_node').order_by(
        F('timestamp_device').desc(nulls_last=True),
        F('packet__timestamp_mqtt').desc()
    )

    online_threshold = timezone.now() - timedelta(minutes=30)

    nodes_data = []
    for pos in latest_positions:
        node = pos.packet.from_node
        if node and pos.latitude is not None and pos.longitude is not None:
            last_message_time = MessagePacket.objects.filter(from_node=node).aggregate(max_ts=Max('timestamp_mqtt'))[
                'max_ts']
            is_online = last_message_time is not None and last_message_time >= online_threshold

            hardware_model_display = node.hardware_model_str if node.hardware_model_str else "N/A"
            role_display = node.role_str if node.role_str else "N/A"

            node_info = {
                'node_id_hex': node.node_id_hex,
                'long_name': node.long_name,
                'short_name': node.short_name,
                'hardware_model': hardware_model_display,
                'role': role_display,
                'last_heard_device': pos.timestamp_device.isoformat() if pos.timestamp_device else None,
                'last_heard_mqtt': pos.packet.timestamp_mqtt.isoformat() if pos.packet and pos.packet.timestamp_mqtt else None,
            }

            latest_telemetry = Telemetry.objects.filter(packet__from_node=node).order_by(
                '-packet__timestamp_mqtt').first()
            telemetry_info = None
            if latest_telemetry:
                telemetry_info = {
                    'battery_level': latest_telemetry.battery_level,
                    'voltage': latest_telemetry.voltage,
                    'air_util_tx': latest_telemetry.air_util_tx,
                    'uptime_seconds': latest_telemetry.uptime_seconds,
                }

            nodes_data.append({
                'id': node.pk,
                'node_id_display': str(node),  # Verwendet die __str__ Methode des Node Modells
                'latitude': pos.latitude,
                'longitude': pos.longitude,
                'altitude': pos.altitude,
                'timestamp_device': pos.timestamp_device.isoformat() if pos.timestamp_device else None,
                'timestamp_mqtt': pos.packet.timestamp_mqtt.isoformat() if pos.packet and pos.packet.timestamp_mqtt else None,
                'is_online': is_online,
                'node_info': node_info,
                'telemetry_info': telemetry_info,
                'packet_id': pos.packet.id if pos.packet else None,
            })
    return JsonResponse({'nodes': nodes_data})


def map_view(request):
    return render(request, 'mqtt_listener/map_view.html')


def dashboard_overview(request):
    latest_position_subquery = Position.objects.filter(
        packet__from_node=OuterRef('pk'),
        latitude__isnull=False,
        longitude__isnull=False
    ).order_by(
        F('timestamp_device').desc(nulls_last=True),
        F('packet__timestamp_mqtt').desc()
    ).values('pk')[:1]

    latest_positions = Position.objects.filter(
        pk__in=Subquery(
            Node.objects.annotate(
                last_pos_id=Subquery(latest_position_subquery)
            ).filter(last_pos_id__isnull=False).values('last_pos_id')
        )
    ).select_related('packet__from_node').order_by(
        F('timestamp_device').desc(nulls_last=True),
        F('packet__timestamp_mqtt').desc()
    )

    recent_messages = MessagePacket.objects.all().select_related(
        'from_node', 'sender_node', 'position_data', 'telemetry_data', 'text_message_data'
    ).order_by('-timestamp_mqtt')[:20]

    node_count = Node.objects.count()
    message_count = MessagePacket.objects.count()
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    recent_activities = MessagePacket.objects.filter(
        timestamp_mqtt__gte=twenty_four_hours_ago
    ).select_related(
        'from_node', 'sender_node', 'position_data', 'telemetry_data', 'text_message_data'
    ).order_by('-timestamp_mqtt')

    context = {
        'nodes_with_last_pos': latest_positions,
        'recent_messages': recent_messages,
        'node_count': node_count,
        'message_count': message_count,
        'recent_activities': recent_activities,
    }
    return render(request, 'mqtt_listener/dashboard_overview.html', context)


def node_list_view(request):
    online_threshold = timezone.now() - timedelta(minutes=30)
    nodes_with_status = Node.objects.annotate(
        last_seen=Max('sent_packets__timestamp_mqtt')
    ).annotate(
        is_online=Case(
            When(last_seen__gte=online_threshold, then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        )
    ).order_by('-is_online', F('last_seen').desc(nulls_last=True), 'long_name', 'short_name')

    paginator = Paginator(nodes_with_status, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {'page_obj': page_obj}
    return render(request, 'mqtt_listener/node_list.html', context)


def node_detail_view(request, node_identifier):
    node = None
    # Normalize the identifier for hex checks (lowercase)
    node_identifier_lower = node_identifier.lower()

    try:
        # 1. Check for 8-char hex ID (e.g., "abcdef12")
        if len(node_identifier_lower) == 8 and all(c in '0123456789abcdef' for c in node_identifier_lower):
            # Assumes node_id_hex is stored WITHOUT '!'
            node = get_object_or_404(Node, node_id_hex=node_identifier_lower)
        # 2. Check for 9-char hex ID with '!' (e.g., "!abcdef12")
        elif node_identifier_lower.startswith('!') and len(node_identifier_lower) == 9 and \
                all(c in '0123456789abcdef' for c in node_identifier_lower[1:]):
            # **FIXED LINE HERE:** Assumes node_id_hex is stored WITH '!'
            node = get_object_or_404(Node, node_id_hex=node_identifier_lower)
        # 3. Try as primary key (integer)
        else:
            try:
                node_pk = int(node_identifier)
                node = get_object_or_404(Node, pk=node_pk)
            except ValueError:
                # If not an int, and not matching hex patterns, it's an invalid format for these checks.
                # We'll proceed to the except block if node is still None after this.
                pass

        if node is None:  # This will be true if none of the above conditions matched or int(node_identifier) failed.
            raise Node.DoesNotExist  # Trigger the except block for fallback

    except (Node.DoesNotExist,
            ValueError):  # Catches DoesNotExist from get_object_or_404 or the explicit raise, ValueError from int()
        # Fallback: More flexible query if specific patterns failed
        q_objects = Q()
        hex_candidate_stripped = node_identifier_lower.replace("!", "")

        if all(c in '0123456789abcdef' for c in hex_candidate_stripped):
            q_objects |= Q(node_id_hex=hex_candidate_stripped)  # Search without '!' (common case)
            if node_identifier_lower.startswith('!'):
                q_objects |= Q(node_id_hex=node_identifier_lower)  # Also search with '!' if provided

        # Try to convert to decimal ID, ensure it's a valid integer string first
        potential_dec_id = node_identifier_lower.replace("!", "")
        if potential_dec_id.isdigit():
            try:
                q_objects |= Q(node_id_dec=int(potential_dec_id))
            except ValueError:  # Should not happen if isdigit() is true, but good practice
                pass

        if not q_objects:  # No valid query conditions could be created from the identifier
            raise Http404("Node not found with the given identifier. The identifier format appears invalid.")

        # Try to get the node with the combined Q objects from fallback logic
        node = get_object_or_404(Node, q_objects)

    messages = MessagePacket.objects.filter(
        Q(from_node=node) | Q(to_node_id_dec=node.node_id_dec) | Q(sender_node=node)
    ).select_related(
        'from_node', 'sender_node', 'position_data', 'telemetry_data', 'text_message_data'
    ).order_by('-timestamp_mqtt')

    paginator = Paginator(messages, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    last_position = Position.objects.filter(packet__from_node=node).order_by(
        F('timestamp_device').desc(nulls_last=True), F('packet__timestamp_mqtt').desc()).first()
    last_telemetry = Telemetry.objects.filter(packet__from_node=node).order_by('-packet__timestamp_mqtt').first()

    online_threshold = timezone.now() - timedelta(minutes=30)
    last_message_time_agg = MessagePacket.objects.filter(
        Q(from_node=node) | Q(sender_node=node)
    ).aggregate(max_ts=Max('timestamp_mqtt'))
    last_message_time = last_message_time_agg['max_ts']
    is_online = last_message_time is not None and last_message_time >= online_threshold

    context = {
        'node': node,
        'page_obj': page_obj,
        'last_position': last_position,
        'last_telemetry': last_telemetry,
        'is_online': is_online,
        'last_message_time': last_message_time,
        'message_count_total': messages.count(),
    }
    return render(request, 'mqtt_listener/node_detail.html', context)


def message_list_view(request):
    all_messages = MessagePacket.objects.all().select_related(
        'from_node', 'sender_node', 'position_data', 'telemetry_data', 'text_message_data'
    )
    query = request.GET.get('q', '')
    message_type_filter = request.GET.get('message_type', '')
    node_filter_str = request.GET.get('node', '')

    if query:
        # Normalize query for hex comparisons
        query_lower = query.lower()
        query_stripped = query_lower.replace("!", "")

        q_filter_query = Q(text_message_data__text__icontains=query) | \
                         Q(from_node__long_name__icontains=query) | \
                         Q(from_node__short_name__icontains=query) | \
                         Q(sender_node__long_name__icontains=query) | \
                         Q(sender_node__short_name__icontains=query)

        # Add hex ID searches, considering presence or absence of '!'
        if all(c in '0123456789abcdef' for c in query_stripped):
            q_filter_query |= Q(from_node__node_id_hex__iexact=query_stripped)
            q_filter_query |= Q(sender_node__node_id_hex__iexact=query_stripped)
            if query_lower.startswith("!"):
                q_filter_query |= Q(from_node__node_id_hex__iexact=query_lower)
                q_filter_query |= Q(sender_node__node_id_hex__iexact=query_lower)

        all_messages = all_messages.filter(q_filter_query).distinct()

    if message_type_filter:
        all_messages = all_messages.filter(message_type=message_type_filter)

    if node_filter_str:
        node_q_objects = Q()
        node_filter_lower = node_filter_str.lower()
        node_filter_hex_stripped = node_filter_lower.replace("!", "")

        # Check if the stripped version is purely hex for node_id_hex search
        if all(c in '0123456789abcdef' for c in node_filter_hex_stripped):
            node_q_objects |= Q(from_node__node_id_hex__iexact=node_filter_hex_stripped)
            node_q_objects |= Q(sender_node__node_id_hex__iexact=node_filter_hex_stripped)
            # If original filter string had '!', also try an exact match with '!'
            if node_filter_lower.startswith('!'):
                node_q_objects |= Q(from_node__node_id_hex__iexact=node_filter_lower)
                node_q_objects |= Q(sender_node__node_id_hex__iexact=node_filter_lower)

        # Try to convert the stripped string to an int for node_id_dec search
        try:
            node_filter_dec = int(node_filter_hex_stripped)
            node_q_objects |= Q(from_node__node_id_dec=node_filter_dec)
            node_q_objects |= Q(to_node_id_dec=node_filter_dec)  # Also check 'to_node_id_dec'
        except ValueError:
            pass  # Not a decimal number

        # Search in long_name and short_name (case-insensitive)
        node_q_objects |= Q(from_node__long_name__icontains=node_filter_str)
        node_q_objects |= Q(from_node__short_name__icontains=node_filter_str)
        node_q_objects |= Q(sender_node__long_name__icontains=node_filter_str)
        node_q_objects |= Q(sender_node__short_name__icontains=node_filter_str)

        if node_q_objects:  # Only apply filter if any Q objects were constructed
            all_messages = all_messages.filter(node_q_objects).distinct()

    all_messages = all_messages.order_by('-timestamp_mqtt')
    paginator = Paginator(all_messages, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    message_types = MessagePacket.objects.values_list('message_type', flat=True).distinct().order_by('message_type')

    context = {
        'page_obj': page_obj,
        'query': query,
        'message_type_filter': message_type_filter,
        'node_filter': node_filter_str,
        'message_types': message_types,
    }
    return render(request, 'mqtt_listener/message_list.html', context)

def documentation_view(request):
    return render(request, 'mqtt_listener/documentation.html')
def privacy_policy_view(request):
    return render(request, 'mqtt_listener/privacy_policy.html')
def imprint_view(request):
    context = {'page_title': 'Imprint'}
    return render(request, 'mqtt_listener/imprint.html', context)
