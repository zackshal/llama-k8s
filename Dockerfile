# Use CUDA 12.4 base image (compatible with driver 550)
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

# Install dependencies for building llama.cpp and Python for MCP
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    python3 \
    python3-pip \
    bc \
    && rm -rf /var/lib/apt/lists/*

# Install Python requests for MCP adapter
RUN pip3 install --no-cache-dir requests

WORKDIR /app

# Clone llama.cpp (specific commit for stability)
RUN git clone https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    git checkout a0ed91a44   # or use latest stable tag

# Build only llama-server with CUDA support (Ada Lovelace arch 89)
WORKDIR /app/llama.cpp
RUN mkdir build && cd build && \
    cmake .. -DLLAMA_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CUDA_ARCH=89 && \
    make -j$(nproc) llama-server

# Copy entrypoint and MCP adapter
COPY entrypoint.sh /entrypoint.sh
COPY mcp_adapter.py /app/mcp_adapter.py
RUN chmod +x /entrypoint.sh /app/mcp_adapter.py

# Expose API port
EXPOSE 8081

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]
