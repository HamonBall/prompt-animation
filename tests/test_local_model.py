"""Streamed inference must finish its plan and report actionable failures."""
import io
import json
import socket
import unittest
import urllib.error
from unittest.mock import patch
from avatar_app.models import PlanError
from avatar_app.planning.local_model import LocalModel, INFERENCE_IDLE_TIMEOUT


def stream(*events):
    return io.BytesIO(b': keepalive\n\n' + b''.join(
        b'data: ' + json.dumps(event).encode('utf-8') + b'\n\n' for event in events)
        + b'data: [DONE]\n\n')


class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.client = LocalModel()
        self.client.endpoint = 'http://127.0.0.1:12345'
        self.addCleanup(self.client.close)
        self.start = patch.object(self.client, 'start').start()
        self.addCleanup(patch.stopall)

    def test_stream_assembles_complete_plan_and_uses_idle_timeout(self):
        progress = []
        response = stream({'choices': [{'delta': {'content': '{"pose":'}}]},
                          {'choices': [{'delta': {'content': '"saluté"}'}}]},
                          {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                          {'choices': [], 'usage': {'completion_tokens': 12}})
        with patch.object(self.client.http, 'open', return_value=response) as open_request:
            content = self.client.complete([], {}, progress.append)
        self.assertEqual(json.loads(content), {'pose': 'saluté'})
        request = open_request.call_args.args[0]
        self.assertTrue(json.loads(request.data)['stream'])
        self.assertEqual(open_request.call_args.kwargs['timeout'], INFERENCE_IDLE_TIMEOUT)
        self.assertIn('Generating motion plan locally', progress)

    def test_unfinished_and_empty_streams_do_not_commit_partial_plans(self):
        responses = [stream({'choices': [{'delta': {'content': '{'}}]}),
                     stream({'choices': [{'delta': {'content': '{}'}, 'finish_reason': 'length'}]}),
                     stream({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}),
                     io.BytesIO(b'data: broken JSON\n\n')]
        for response in responses:
            with self.subTest(response=response), patch.object(self.client.http, 'open', return_value=response):
                with self.assertRaises(PlanError):
                    self.client.complete([], {})

    def test_connection_timeout_and_http_errors_are_distinct(self):
        failures = [(socket.timeout(), 'stopped responding'),
                    (urllib.error.URLError(socket.timeout()), 'stopped responding'),
                    (urllib.error.URLError('connection refused'), 'connection.*lost'),
                    (urllib.error.HTTPError(self.client.endpoint, 503, 'busy', {}, None), 'HTTP 503')]
        for error, message in failures:
            with self.subTest(error=error), patch.object(self.client.http, 'open', side_effect=error):
                with self.assertRaisesRegex(PlanError, message):
                    self.client.complete([], {})

    def test_response_size_is_bounded(self):
        response = io.BytesIO(b':' + b'x' * (1024 * 1024))
        with patch.object(self.client.http, 'open', return_value=response):
            with self.assertRaisesRegex(PlanError, 'oversized'):
                self.client.complete([], {})


if __name__ == '__main__':
    unittest.main()
