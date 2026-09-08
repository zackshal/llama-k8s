#!/bin/bash
set -euo pipefail

# ======================================================================
# Use virtual environment's Python if available
# ======================================================================
export PATH="${VENV_PATH:-/opt/venv}/bin:$PATH"

# ======================================================================
# Fully automated entrypoint for llamaserver
# All parameters are computed from live system data and model metadata
# ======================================================================

#  1. System detection functions 

detect_cpu_cores() {
    local phys=$(lscpu | grep -E "^Core\(s\) per socket:" | awk '{print $4}')
    local sockets=$(lscpu | grep -E "^Socket\(s\):" | awk '{print $2}')
    if [[ -n "$phys" && -n "$sockets" ]]; then
        echo $((phys * sockets))
    else
        echo $(($(nproc 2>/dev/null || echo 4) / 2))
    fi
}

detect_total_ram_mb() { free -m | awk '/^Mem:/{print $2}'; }
detect_available_ram_mb() { free -m | awk '/^Mem:/{print $7}'; }

detect_gpu_info() {
    if command -v nvidia-smi &>/dev/null; then
        local total=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1)
        local used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -n1)
        local free=$((total - used))
        echo "GPU_TOTAL=$total GPU_USED=$used GPU_FREE=$free"
    else
        echo "GPU_TOTAL=0 GPU_USED=0 GPU_FREE=0"
    fi
}

#  2. Gather system information 

PHYSICAL_CORES=$(detect_cpu_cores)
LOGICAL_CORES=$(nproc 2>/dev/null || echo 4)
TOTAL_RAM_MB=$(detect_total_ram_mb)
AVAIL_RAM_MB=$(detect_available_ram_mb)
GPU_INFO=$(detect_gpu_info)
eval "$GPU_INFO"  # sets GPU_TOTAL, GPU_USED, GPU_FREE
GPU_FREE=${GPU_FREE:-0}
GPU_TOTAL=${GPU_TOTAL:-0}

#  3. Model detection and metadata extraction 

MODEL_DIR="${MODEL_DIR:-/models}"
if [[ -z "${MODEL_NAME:-}" ]]; then
    # Поиск моделей разных форматов
    MODEL_PATH=$(find "$MODEL_DIR" -maxdepth 1 -type f \( -name "*.gguf" -o -name "*.safetensors" -o -name "*.bin" \) | head -n1)
    if [[ -z "$MODEL_PATH" ]]; then
        echo "ERROR: No model file found in $MODEL_DIR and MODEL_NAME not set."
        exit 1
    fi
else
    MODEL_PATH="$MODEL_DIR/$MODEL_NAME"
    if [[ ! -f "$MODEL_PATH" ]]; then
        echo "ERROR: Model file $MODEL_PATH not found."
        exit 1
    fi
fi

# Extract model metadata using model_detector.py
if command -v python3 &>/dev/null && [[ -f /app/model_detector.py ]]; then
    MODEL_JSON=$(python3 /app/model_detector.py "$MODEL_PATH")
    # Parse JSON fields (используем правильные имена полей)
    NUM_LAYERS=$(echo "$MODEL_JSON" | jq -r '.num_layers // 32')
    EMBEDDING_LENGTH=$(echo "$MODEL_JSON" | jq -r '.embedding_length // 4096')
    FILE_SIZE_MB=$(echo "$MODEL_JSON" | jq -r '.file_size_mb // 5000')
    ARCH=$(echo "$MODEL_JSON" | jq -r '.architecture // "unknown"')
    SIZE_LABEL=$(echo "$MODEL_JSON" | jq -r '.size_label // "unknown"')
    # Если jq не сработал или поля null, используем fallback
    if [[ -z "$NUM_LAYERS" || "$NUM_LAYERS" == "null" ]]; then
        NUM_LAYERS=32
        EMBEDDING_LENGTH=4096
        FILE_SIZE_MB=$(stat -c %s "$MODEL_PATH" 2>/dev/null | awk '{print int($1/1048576)}')
        SIZE_LABEL="unknown"
    fi
else
    # Fallback: use file size and guess
    NUM_LAYERS=32
    EMBEDDING_LENGTH=4096
    FILE_SIZE_MB=$(stat -c %s "$MODEL_PATH" 2>/dev/null | awk '{print int($1/1048576)}')
    SIZE_LABEL="unknown"
fi

# Ensure variables are numbers
if [[ -z "$NUM_LAYERS" || "$NUM_LAYERS" == "null" ]]; then NUM_LAYERS=32; fi
if [[ -z "$FILE_SIZE_MB" || "$FILE_SIZE_MB" == "null" || "$FILE_SIZE_MB" -eq 0 ]]; then FILE_SIZE_MB=5000; fi

#  4. CPU thread optimization 

if [[ $LOGICAL_CORES -gt $PHYSICAL_CORES ]]; then HT_ENABLED=1; else HT_ENABLED=0; fi
L3_CACHE_KB=$(lscpu | grep -E "^L3 cache:" | awk '{print $3}' | sed 's/[^0-9]//g')
L3_CACHE_KB=${L3_CACHE_KB:-0}

if [[ $L3_CACHE_KB -gt 20000 ]]; then
    THREADS_RECOMMENDED=$((PHYSICAL_CORES * 150 / 100))
else
    THREADS_RECOMMENDED=$((PHYSICAL_CORES * 90 / 100))
fi
if [[ $THREADS_RECOMMENDED -lt 2 ]]; then THREADS_RECOMMENDED=2; fi
if [[ $THREADS_RECOMMENDED -gt 64 ]]; then THREADS_RECOMMENDED=64; fi

THREADS_BATCH_RECOMMENDED=$((THREADS_RECOMMENDED * 120 / 100))
if [[ $THREADS_BATCH_RECOMMENDED -gt $LOGICAL_CORES ]]; then
    THREADS_BATCH_RECOMMENDED=$LOGICAL_CORES
fi
if [[ $THREADS_BATCH_RECOMMENDED -lt 2 ]]; then THREADS_BATCH_RECOMMENDED=2; fi

THREADS=${THREADS:-$THREADS_RECOMMENDED}
THREADS_BATCH=${THREADS_BATCH:-$THREADS_BATCH_RECOMMENDED}

#  5. GPU offloading and context calculation 

# VRAM safety margin
VRAM_SAFETY=200
VRAM_AVAILABLE=$((GPU_FREE - VRAM_SAFETY))
if [[ $VRAM_AVAILABLE -lt 0 ]]; then VRAM_AVAILABLE=0; fi

# Estimate VRAM per layer: total file size / number of layers (rough)
if [[ $NUM_LAYERS -gt 0 ]]; then
    VRAM_PER_LAYER=$((FILE_SIZE_MB / NUM_LAYERS))
else
    VRAM_PER_LAYER=150
fi
if [[ $VRAM_PER_LAYER -eq 0 ]]; then VRAM_PER_LAYER=150; fi

# Determine number of layers to offload (ngl)
if [[ $VRAM_AVAILABLE -ge $FILE_SIZE_MB ]]; then
    NGL=99
else
    NGL=$((VRAM_AVAILABLE / VRAM_PER_LAYER))
    if [[ $NGL -gt 99 ]]; then NGL=99; fi
    if [[ $NGL -lt 0 ]]; then NGL=0; fi
fi

if [[ $VRAM_AVAILABLE -lt 200 ]]; then
    NGL=0
fi

# Compute context length based on remaining VRAM after offloading
if [[ $NGL -gt 0 ]]; then
    MODEL_USED_VRAM=$((NGL * VRAM_PER_LAYER))
    REMAINING_VRAM=$((VRAM_AVAILABLE - MODEL_USED_VRAM))
    if [[ $REMAINING_VRAM -lt 0 ]]; then REMAINING_VRAM=0; fi
    # Compute KV cache per token in MB
    KV_MB_PER_TOKEN=$(echo "scale=4; (2 * $NUM_LAYERS * $EMBEDDING_LENGTH * 0.5) / (1024*1024)" | bc)
    if [[ -z "$KV_MB_PER_TOKEN" || "$KV_MB_PER_TOKEN" == "0" ]]; then
        KV_MB_PER_TOKEN=0.45
    fi
    MAX_CONTEXT=$(echo "$REMAINING_VRAM / $KV_MB_PER_TOKEN" | bc)
    if [[ $MAX_CONTEXT -gt 16384 ]]; then MAX_CONTEXT=16384; fi
    if [[ $MAX_CONTEXT -lt 512 ]]; then MAX_CONTEXT=512; fi
else
    # CPU-only: use system RAM
    RAM_AVAIL_MB=$AVAIL_RAM_MB
    KV_RAM_MB=$((RAM_AVAIL_MB / 2))
    KV_MB_PER_TOKEN_CPU=0.9  # estimate
    MAX_CONTEXT=$((KV_RAM_MB / KV_MB_PER_TOKEN_CPU))
    if [[ $MAX_CONTEXT -gt 8192 ]]; then MAX_CONTEXT=8192; fi
    if [[ $MAX_CONTEXT -lt 512 ]]; then MAX_CONTEXT=512; fi
fi

if [[ -n "${CONTEXT:-}" ]]; then
    if [[ $CONTEXT -gt $MAX_CONTEXT ]]; then
        echo "WARNING: Requested context $CONTEXT exceeds computed max ($MAX_CONTEXT). Reducing."
        CONTEXT=$MAX_CONTEXT
    fi
else
    CONTEXT=$MAX_CONTEXT
fi

# Batch size
if [[ $GPU_TOTAL -gt 6000 ]]; then
    BATCH=${BATCH:-512}
else
    BATCH=${BATCH:-256}
fi

# Other parameters
PARALLEL=${PARALLEL:-1}
FLASH_ATTN=${FLASH_ATTN:-on}
CACHE_TYPE_K=${CACHE_TYPE_K:-q4_0}
CACHE_TYPE_V=${CACHE_TYPE_V:-q4_0}
CONT_BATCHING="${CONT_BATCHING:---cont-batching}"
MLOCK="${MLOCK:---mlock}"

#  6. Display computed settings 
echo "=============================================="
echo "Auto-optimized settings for llama-server"
echo "=============================================="
echo "Model path: $MODEL_PATH"
echo "Architecture: ${ARCH:-unknown}"
echo "Size label: ${SIZE_LABEL:-unknown}"
echo "Layers (blocks): $NUM_LAYERS"
echo "Embedding length: $EMBEDDING_LENGTH"
echo "File size (est. VRAM): $FILE_SIZE_MB MiB"
echo "Physical cores: $PHYSICAL_CORES"
echo "Logical cores: $LOGICAL_CORES"
echo "L3 cache: ${L3_CACHE_KB:-unknown} KB"
echo "Total RAM: $TOTAL_RAM_MB MiB"
echo "Available RAM: $AVAIL_RAM_MB MiB"
echo "GPU total VRAM: $GPU_TOTAL MiB"
echo "GPU free VRAM: $GPU_FREE MiB"
echo "Offloaded layers (ngl): $NGL"
echo "Context length: $CONTEXT"
echo "Batch size: $BATCH"
echo "Threads: $THREADS"
echo "Threads-batch: $THREADS_BATCH"
echo "Parallel slots: $PARALLEL"
echo "Flash attention: $FLASH_ATTN"
echo "Cache type K/V: $CACHE_TYPE_K / $CACHE_TYPE_V"
echo "Contiguous batching: $CONT_BATCHING"
echo "MLock: $MLOCK"
echo "=============================================="

#  7. Launch llamaserver 
LLAMA_SERVER="${LLAMA_SERVER_PATH:-/app/llama.cpp/build/bin/llama-server}"

CMD="$LLAMA_SERVER \
    -m \"$MODEL_PATH\" \
    --host \"${HOST:-0.0.0.0}\" \
    --port \"${PORT:-8081}\" \
    -ngl $NGL \
    -c $CONTEXT \
    -b $BATCH \
    --parallel $PARALLEL \
    --threads $THREADS \
    --threads-batch $THREADS_BATCH \
    --flash-attn $FLASH_ATTN \
    --cache-type-k $CACHE_TYPE_K \
    --cache-type-v $CACHE_TYPE_V \
    $CONT_BATCHING \
    $MLOCK \
    --verbose"

echo "Starting llama-server with command:"
echo "$CMD"
eval "$CMD" &
LLAMA_PID=$!

#  8. Optional MCP server 
if [[ "${MCP_ENABLED:-0}" == "1" ]]; then
    echo "MCP server enabled. Starting MCP adapter..."
    if [[ -f "/app/mcp_adapter.py" ]]; then
        python3 /app/mcp_adapter.py --llama-url "http://localhost:${PORT:-8081}" &
        MCP_PID=$!
        echo "MCP adapter started (PID $MCP_PID)"
    else
        echo "WARNING: MCP_ENABLED=1 but /app/mcp_adapter.py not found."
    fi
fi

#  9. Wait 
wait $LLAMA_PID
