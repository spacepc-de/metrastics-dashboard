# metrastics_commander/urls.py
from django.urls import path
from . import views

app_name = 'metrastics_commander'

urlpatterns = [
    path('', views.commander_page, name='commander_page'),
    # API Endpoints for Commander Rules
    path('api/rules/', views.api_get_commander_rules, name='api_get_commander_rules'), # GET all rules
    path('api/rules/<int:rule_id>/', views.api_commander_rule_detail, name='api_commander_rule_detail'), # GET single rule
    path('api/rules/<int:rule_id>/update/', views.api_update_commander_rule, name='api_update_commander_rule'), # POST to update
    path('api/rules/<int:rule_id>/delete/', views.api_delete_commander_rule, name='api_delete_commander_rule'), # POST to delete
    path('api/chatbot-mode/', views.api_chatbot_mode, name='api_chatbot_mode'),
]