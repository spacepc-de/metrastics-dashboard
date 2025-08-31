from django.test import TestCase
from django.urls import reverse
import json

from .models import CommanderSettings


class ChatbotModeAPITestCase(TestCase):
    def setUp(self):
        self.url = reverse('metrastics_commander:api_chatbot_mode')

    def test_toggle_chatbot_mode(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['enabled'])

        response = self.client.post(self.url, data=json.dumps({'enabled': True}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['enabled'])
        self.assertTrue(CommanderSettings.get_solo().chatbot_mode_enabled)

        response = self.client.post(self.url, data=json.dumps({'enabled': False}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['enabled'])
