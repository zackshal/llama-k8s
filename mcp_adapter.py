#!/usr/bin/env python3
"""Authenticated HTTP completion adapter; this is not an MCP protocol server."""
import hmac
import os
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
import requests


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 65536
    key_file = os.environ.get('LLAMA_ADAPTER_KEY_FILE', '')
    if not key_file:
        raise RuntimeError('LLAMA_ADAPTER_KEY_FILE is required')
    with open(key_file, encoding='utf-8') as stream:
        key = stream.read().strip()
    if len(key) < 32 or any(c in key for c in '\r\n'):
        raise RuntimeError('Adapter key must contain at least 32 characters without newlines')
    upstream = os.environ.get('LLAMA_URL', 'http://127.0.0.1:8081').rstrip('/')
    parsed = urlsplit(upstream)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError('Invalid LLAMA_URL')
    session = requests.Session()
    session.trust_env = False

    @app.before_request
    def authenticate():
        if request.path != '/livez' and not hmac.compare_digest(
                request.headers.get('Authorization', '').encode('utf-8'), ('Bearer ' + key).encode('utf-8')):
            return jsonify(error='Unauthorized'), 401

    @app.get('/livez')
    def live():
        return jsonify(status='alive')

    @app.get('/health')
    def ready():
        try:
            result = session.get(upstream + '/health', timeout=(3, 5), allow_redirects=False)
            if result.status_code == 200:
                return jsonify(status='ready')
        except requests.RequestException:
            pass
        return jsonify(status='unavailable'), 503

    @app.post('/complete')
    def complete():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get('prompt'), str) or not 1 <= len(data['prompt']) <= 32768:
            return jsonify(error='Invalid prompt'), 400
        tokens = data.get('max_tokens', 512)
        temperature = data.get('temperature', 0.7)
        stop = data.get('stop', [])
        if (type(tokens) is not int or not 1 <= tokens <= 4096
                or type(temperature) not in (int, float) or not 0 <= temperature <= 2
                or not isinstance(stop, list) or len(stop) > 8
                or any(not isinstance(x, str) or len(x) > 128 for x in stop)):
            return jsonify(error='Invalid generation parameters'), 400
        try:
            result = session.post(upstream + '/completion', json={
                'prompt': data['prompt'], 'n_predict': tokens,
                'temperature': temperature, 'stop': stop,
            }, timeout=(3, 120), allow_redirects=False)
            if result.status_code != 200:
                return jsonify(error='Upstream unavailable'), 502
            body = result.json()
            if not isinstance(body, dict) or not isinstance(body.get('content'), str):
                return jsonify(error='Invalid upstream response'), 502
            return jsonify(content=body['content'])
        except (requests.RequestException, ValueError):
            return jsonify(error='Upstream unavailable'), 502

    return app


if __name__ == '__main__':
    raise SystemExit('Use gunicorn --bind 127.0.0.1:8082 "mcp_adapter:create_app()"')
