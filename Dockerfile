# Use CUDA 12.4 base image (compatible with driver 550)
ARG BASE_IMAGE=nvidia/cuda:12.4.0-devel-ubuntu22.04
FROM ${BASE_IMAGE}

# Arg for version of llama.cpp (tag or hash)
ARG LLAMA_CPP_VERSION=master

# Install system dependencies for building llama.cpp and Python tools
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    bc \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Setup Python virtual environment
ENV VENV_PATH=/opt/venv
RUN python3 -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Build llama.cpp (CUDA)
WORKDIR /app
RUN git clone https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    if [ "$LLAMA_CPP_VERSION" != "master" ]; then \
        git checkout "$LLAMA_CPP_VERSION"; \
    fi

WORKDIR /app/llama.cpp
RUN mkdir build && cd build && \
    cmake .. -DLLAMA_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CUDA_ARCH=89 && \
    make -j$(nproc) llama-server

COPY entrypoint.sh /entrypoint.sh
COPY model_detector.py /app/model_detector.py
COPY mcp_adapter.py /app/mcp_adapter.py
RUN chmod +x /entrypoint.sh /app/model_detector.py /app/mcp_adapter.py

# Expose API port
EXPOSE 8081

# Use the virtual environment's python in entrypoint (via PATH)
ENTRYPOINT ["/entrypoint.sh"]
