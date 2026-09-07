#!/usr/bin/env python3
"""
MCP (Model Context Protocol) HTTP adapter for llama.cpp.
Listens on port 8082 and forwards completion requests to llama-server.
"""
import argparse
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
LLAMA_URL = "http://localhost:8081"

@app.route("/complete", methods=["POST"])
def complete():
    """MCP-style completion endpoint."""
    data = request.get_json()
    if not data or "prompt" not in data:
        return jsonify({"error": "Missing 'prompt'"}), 400

    # Forward to llama-server
    payload = {
        "prompt": data["prompt"],
        "n_predict": data.get("max_tokens", 512),
        "temperature": data.get("temperature", 0.7),
        "stop": data.get("stop", [])
    }
    try:
        resp = requests.post(f"{LLAMA_URL}/completion", json=payload, timeout=120)
        if resp.status_code == 200:
            return jsonify({"content": resp.json().get("content", "")})
        else:
            return jsonify({"error": f"llama-server returned {resp.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llama-url", default="http://localhost:8081", help="URL of llama-server")
    parser.add_argument("--port", type=int, default=8082, help="Port to listen on")
    args = parser.parse_args()
    LLAMA_URL = args.llama_url
    app.run(host="0.0.0.0", port=args.port)
