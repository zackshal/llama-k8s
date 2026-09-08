# Use CUDA 12.4 base image (compatible with driver 550)
ARG BASE_IMAGE=nvidia/cuda:12.4.0-devel-ubuntu22.04
FROM ${BASE_IMAGE}

# Arg for version of llama.cpp (tag or hash)
ARG LLAMA_CPP_VERSION=master

# Install dependencies for building llama.cpp and Python for MCP
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    python3 \
    python3-pip \
    bc \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python requests for MCP adapter with gguf work models
RUN pip3 install --no-cache-dir requests gguf safetensors

WORKDIR /app

# Clone llama.cpp (specific commit for stability)
RUN git clone https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    if [ "$LLAMA_CPP_VERSION" != "master"]; then \
	git checkout $LLAMA_CPP_VERSION; \
    fi

# Build only llama-server with CUDA support (Ada Lovelace arch 89)
WORKDIR /app/llama.cpp
RUN mkdir build && cd build && \
    cmake .. -DLLAMA_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CUDA_ARCH=89 && \
    make -j$(nproc) llama-server

# Copy entrypoint and MCP adapter
COPY entrypoint.sh /entrypoint.sh
COPY model_detector.py /app/model_detector.py
COPY mcp_adapter.py /app/mcp_adapter.py
RUN chmod +x /entrypoint.sh /app/mcp_adapter.py /app/mcp_adapter.py

# Expose API port
EXPOSE 8081

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]
