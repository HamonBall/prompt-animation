"""Owned, loopback-only llama.cpp process. No model installation on import."""
import atexit
import json
import secrets
import socket
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request

from ..models import PlanError


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / '.runtime'
MODEL = RUNTIME / 'Qwen3-4B-Q4_K_M.gguf'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalModel:
    def __init__(self):
        self.process = None
        self.log = None
        self.lock = threading.Lock()
        self.api_key = secrets.token_hex(24)
        self.endpoint = None
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        atexit.register(self.close)

    def _request(self, path, data=None, timeout=2):
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(data, allow_nan=False).encode('utf-8') if data is not None else None,
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + self.api_key})
        with self.http.open(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise PlanError('The local model returned an oversized response.')
            return json.loads(raw)

    def _ready(self):
        if self.endpoint is None:
            return False
        try:
            data = self._request('/v1/models')
            return any(model.get('id') == 'avatar-qwen' for model in data.get('data', []))
        except (OSError, ValueError):
            return False

    def start(self):
        if self._ready():
            return
        executable = RUNTIME / 'llama' / 'llama-server.exe'
        if not executable.is_file() or not MODEL.is_file():
            raise PlanError('Local AI is not installed. Run tools/setup_local_ai.ps1. '
                            'Existing short commands still work.')
        if self.process is None or self.process.poll() is not None:
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0))
                port = port_socket.getsockname()[1]
            self.endpoint = f'http://127.0.0.1:{port}'
            if self.log:
                self.log.close()
            self.log = (RUNTIME / 'server.log').open('ab')
            self.process = subprocess.Popen([
                str(executable), '--model', str(MODEL), '--alias', 'avatar-qwen',
                '--host', '127.0.0.1', '--port', str(port), '--ctx-size', '8192',
                '--threads', '3', '--parallel', '1', '--n-gpu-layers', '0',
                '--api-key', self.api_key,
            ], stdout=self.log, stderr=self.log, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self._ready():
                return
            if self.process.poll() is not None:
                raise PlanError('The local AI runtime could not start. See .runtime/server.log.')
            time.sleep(0.2)
        raise PlanError('Local AI is still loading. Try again shortly; your animation is unchanged.')

    def complete(self, messages, schema):
        with self.lock:
            try:
                if sum(len(message.get('content', '')) for message in messages) > 22000:
                    raise PlanError('This plan is too large for local interpretation. Edit fewer stages at a time.')
                self.start()
                data = self._request('/v1/chat/completions', {
                    'model': 'avatar-qwen', 'messages': messages,
                    'temperature': 0, 'seed': 42,
                    'max_tokens': 1800 if 'stages' in schema.get('properties', {}) else 600,
                    'chat_template_kwargs': {'enable_thinking': False},
                    'response_format': {'type': 'json_object', 'schema': schema},
                    'stream': False,
                }, timeout=300)
                choice = data['choices'][0]
                if choice.get('finish_reason') != 'stop':
                    raise PlanError('Local AI did not finish its plan. Try a shorter request.')
                return choice['message']['content']
            except PlanError:
                raise
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                raise PlanError('Local AI could not complete this request. '
                                'Your animation is unchanged; try again or use a short command.') from exc

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.log:
            self.log.close()
            self.log = None


_client = None


def get_model():
    global _client
    if _client is None:
        _client = LocalModel()
    return _client
