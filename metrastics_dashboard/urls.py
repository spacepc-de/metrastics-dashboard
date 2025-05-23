# metrastics_dashboard/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('nodes/', views.nodes_page, name='nodes_page'),
    path('map/', views.map_page, name='map_page'),  # New URL for the Map page
    path('api/connection_status/', views.api_connection_status, name='api_connection_status'),
    path('api/counters/', views.api_counters, name='api_counters'),
    path('api/nodes/', views.api_nodes, name='api_nodes'),
    path('api/all_nodes/', views.api_get_all_nodes, name='api_get_all_nodes'),
    path('api/node_detail/<str:node_id>/', views.api_node_detail, name='api_node_detail'),
    path('api/live_packets/', views.api_live_packets, name='api_live_packets'),
    path('api/average_signal_stats/', views.api_average_signal_stats, name='api_average_signal_stats'),
]