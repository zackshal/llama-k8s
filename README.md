# 🦙 llama.cpp Docker with Auto-Optimization & MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CUDA](https://img.shields.io/badge/CUDA-12.4-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![K3s](https://img.shields.io/badge/K3s-ready-blue.svg)](https://k3s.io/)

> **Production-ready Docker container for llama.cpp with automatic hardware optimization, GPU acceleration, and MCP (Model Context Protocol) adapter.**

---

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Architecture](#-architecture)
- [Auto-Optimization](#-auto-optimization)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [MCP Adapter](#-mcp-adapter)
- [Kubernetes / K3s Deployment](#-kubernetes--k3s-deployment)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## ✨ Features

- **Fully automatic optimization** — detects CPU cores, RAM, GPU VRAM, and model file to compute optimal parameters (`-ngl`, `-c`, `-b`, `--threads`, etc.)
- **Multi-model support** — works with any `.gguf` model (not just Dolphin) — auto-detects quantization from filename (Q4_K_M, Q5_K_M, Q6_K, Q8_0, etc.)
- **GPU acceleration** — CUDA 12.4 with Ada Lovelace (arch 89) support
- **MCP adapter** — HTTP server for Model Context Protocol integration (agents, coding assistants)
- **Kubernetes/K3s ready** — full set of manifests for production deployment
- **Lightweight** — single container, minimal overhead

---

## 🚀 Quick Start

### With Docker Compose

```bash
# Clone the repository
git clone https://github.com/yourusername/llama-cpp-docker.git
cd llama-cpp-docker

# Place your .gguf model in ./models/ directory
# (or mount your existing models directory)

# Build and run
docker-compose up --build
