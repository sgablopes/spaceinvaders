import unittest
from unittest.mock import patch

from app import create_app
from app.services.engine import EngineResult, EngineUnavailableError


class AssistantTest(unittest.TestCase):
    def setUp(self):
        self.client=create_app({'TESTING':True}).test_client()
        self.body={'message':'Como está minha lavoura?','context':{'property':{'name':'Sítio'}},'history':[],'language':'pt-BR'}

    @patch('app.api.assistant.AgrionEngine')
    def test_message_passes_context_and_returns_response(self, engine):
        engine.return_value.run.return_value=EngineResult('Resposta','model',('buscar_culturas',))
        response=self.client.post('/api/assistant/message',json=self.body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['tools_used'],['buscar_culturas'])
        self.assertEqual(engine.return_value.run.call_args.kwargs['context'],self.body['context'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    @patch('app.api.assistant.AgrionEngine')
    def test_service_failure_does_not_expose_details(self, engine):
        engine.return_value.run.side_effect=EngineUnavailableError('detalhe interno')
        response=self.client.post('/api/assistant/message',json=self.body)
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json,{'error':'assistant_unavailable'})
