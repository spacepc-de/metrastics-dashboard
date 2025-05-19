# mqtt_listener/urls.py
from django.urls import path
from . import views

app_name = 'mqtt_listener'

urlpatterns = [
    path('', views.dashboard_overview, name='dashboard_overview'),
    path('nodes/', views.node_list_view, name='node_list'),
    path('nodes/<str:node_identifier>/', views.node_detail_view, name='node_detail'),
    path('messages/', views.message_list_view, name='message_list'),
    path('map/', views.map_view, name='map_view'),
    # NEU HINZUFÜGEN:
    path('api/node-positions/', views.get_node_positions_for_map, name='api_node_positions'),
    path('documentation/', views.documentation_view, name='documentation'),
    path('privacy-policy/', views.privacy_policy_view, name='privacy_policy'),
    path('imprint/', views.imprint_view, name='imprint'),
]