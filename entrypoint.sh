#!/usr/bin/env bash
set -euo pipefail

server="${LLAMA_SERVER_PATH:-/app/llama-server}"
if [[ ! -x "$server" ]]; then
  echo "llama-server executable is missing" >&2
  exit 1
fi
if [[ "${MCP_ENABLED:-0}" != 0 ]]; then
  echo "Run the authenticated adapter as a separate supervised service" >&2
  exit 1
fi
if (( $# )); then
  exec "$server" "$@"
fi
model_name="${MODEL_NAME:-}"
if [[ ! "$model_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.gguf$ ]]; then
  echo "Set MODEL_NAME to one explicit GGUF filename" >&2
  exit 1
fi
model_path="${MODEL_DIR:-/models}/$model_name"
if [[ ! -f "$model_path" || ! -r "$model_path" ]]; then
  echo "The selected model is not a readable regular file" >&2
  exit 1
fi
threads="${THREADS:-2}"
context="${CONTEXT:-2048}"
ngl="${NGL:-0}"
if [[ ! "$threads" =~ ^[1-9][0-9]{0,2}$ || ! "$context" =~ ^[1-9][0-9]{0,5}$ || ! "$ngl" =~ ^[0-9]{1,3}$ ]]; then
  echo "THREADS, CONTEXT and NGL must be bounded decimal integers" >&2
  exit 1
fi
if (( 10#$threads > 256 || 10#$context < 128 || 10#$context > 131072 || 10#$ngl > 999 )); then
  echo "Runtime settings are outside supported bounds" >&2
  exit 1
fi
args=(-m "$model_path" --host "${HOST:-0.0.0.0}" --port "${PORT:-8081}"
      --threads "$threads" -c "$context" -ngl "$ngl")
exec "$server" "${args[@]}"
