ARG BASE_IMAGE
ARG RUNTIME_IMAGE
FROM ${BASE_IMAGE} AS build
ARG LLAMA_CPP_VERSION
ARG GGML_CUDA=OFF
ARG BUILD_JOBS=2
RUN printf '%s' "$LLAMA_CPP_VERSION" | grep -Eq '^[a-f0-9]{40}$' \
    && printf '%s' "$GGML_CUDA" | grep -Eq '^(ON|OFF)$' \
    && printf '%s' "$BUILD_JOBS" | grep -Eq '^[1-9][0-9]?$'
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git init llama.cpp && cd llama.cpp \
    && git remote add origin https://github.com/ggml-org/llama.cpp.git \
    && git fetch --depth 1 origin "$LLAMA_CPP_VERSION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$LLAMA_CPP_VERSION"
RUN cmake -S llama.cpp -B out -DGGML_CUDA="$GGML_CUDA" \
      -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build out --target llama-server --parallel "$BUILD_JOBS"

FROM ${RUNTIME_IMAGE} AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 llama \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin llama
WORKDIR /app
COPY --from=build /build/out/bin/llama-server /app/llama-server
COPY --chmod=755 entrypoint.sh /entrypoint.sh
USER 10001:10001
EXPOSE 8081
ENTRYPOINT ["/entrypoint.sh"]
