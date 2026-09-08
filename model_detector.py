#!/usr/bin/env python3
"""
Universal model metadata extractor for llama.cpp inference server.
Supports GGUF, Safetensors (with config.json), PyTorch .bin (with config.json),
ONNX (limited), and fallback based on file size.
"""

import sys
import json
import os
import pathlib
import struct
import warnings

# Try to import optional dependencies
try:
    from gguf import GGUFReader
except ImportError:
    GGUFReader = None
    warnings.warn("gguf module not installed; GGUF parsing disabled")

try:
    import safetensors
except ImportError:
    safetensors = None
    warnings.warn("safetensors module not installed; Safetensors parsing disabled")

try:
    import onnx
except ImportError:
    onnx = None
    warnings.warn("onnx module not installed; ONNX parsing disabled")


def detect_format(path: str) -> str:
    """
    Detect model format by magic bytes and/or file extension.
    """
    ext = pathlib.Path(path).suffix.lower()
    with open(path, 'rb') as f:
        head = f.read(12)
        # GGUF magic: "GGUF" (0x47 0x47 0x55 0x46) or "__gguf__"
        if head[:4] == b'GGUF' or head[:8] == b'__gguf__':
            return 'gguf'
        # Safetensors: starts with a 64-bit length then JSON
        if ext == '.safetensors':
            return 'safetensors'
        # PyTorch .bin, .pt, .pth – check for config.json
        if ext in ('.bin', '.pt', '.pth'):
            config_path = pathlib.Path(path).with_name('config.json')
            if config_path.exists():
                return 'pytorch'
            else:
                return 'unknown'
        if ext == '.onnx':
            return 'onnx'
    return 'unknown'


def parse_gguf(path: str) -> dict:
    """
    Extract metadata from a GGUF model file.
    """
    if GGUFReader is None:
        raise RuntimeError("gguf module not available")
    reader = GGUFReader(path)
    meta = reader.metadata

    arch = meta.get('general.architecture', 'unknown')
    n_layers = meta.get('llama.block_count', meta.get('bert.block_count', 0))
    hidden = meta.get('llama.embedding_length', meta.get('bert.embedding_length', 0))
    ctx = meta.get('llama.context_length', meta.get('bert.context_length', 2048))
    quant = meta.get('general.quantization', 'unknown')
    
    # Try to get exact parameter count from metadata
    n_params = meta.get('general.parameter_count', 0)
    if n_params == 0 and n_layers and hidden:
        # Rough estimate for LLaMA-like architectures
        # P ≈ n_layers * (12 * hidden^2) + vocab_size * hidden
        vocab = meta.get('llama.vocab_size', meta.get('bert.vocab_size', 32000))
        n_params = int(n_layers * (12 * hidden * hidden) + vocab * hidden)

    file_size_mb = os.path.getsize(path) // (1024 * 1024)

    return {
        'format': 'gguf',
        'architecture': arch,
        'num_layers': n_layers,
        'embedding_length': hidden,
        'num_parameters': n_params,
        'file_size_mb': file_size_mb,
        'quantization': quant,
        'context_length': ctx,
    }


def parse_safetensors(path: str) -> dict:
    """
    Extract metadata from a Safetensors file with config.json.
    """
    if safetensors is None:
        raise RuntimeError("safetensors module not available")
    
    # Read metadata from safetensors (JSON block)
    with open(path, 'rb') as f:
        length_bytes = f.read(8)
        if len(length_bytes) < 8:
            raise ValueError("Invalid safetensors file")
        length = struct.unpack('<Q', length_bytes)[0]
        meta_json = f.read(length).decode('utf-8')
        meta = json.loads(meta_json)
    
    # Look for config.json
    config_path = pathlib.Path(path).with_name('config.json')
    if config_path.exists():
        with open(config_path, 'r') as cf:
            config = json.load(cf)
        
        arch = config.get('architectures', ['unknown'])[0]
        n_layers = config.get('num_hidden_layers', 0)
        hidden = config.get('hidden_size', 0)
        ctx = config.get('max_position_embeddings', 2048)
        n_params = config.get('num_parameters', 0)
        vocab = config.get('vocab_size', 32000)
        
        if n_params == 0 and n_layers and hidden:
            # Estimate based on architecture
            n_params = int(n_layers * (12 * hidden * hidden) + vocab * hidden)
        
        file_size_mb = os.path.getsize(path) // (1024 * 1024)
        return {
            'format': 'safetensors',
            'architecture': arch,
            'num_layers': n_layers,
            'embedding_length': hidden,
            'num_parameters': n_params,
            'file_size_mb': file_size_mb,
            'quantization': 'unknown',
            'context_length': ctx,
        }
    else:
        # No config.json, fallback
        return {
            'format': 'safetensors',
            'architecture': 'unknown',
            'num_layers': 0,
            'embedding_length': 0,
            'num_parameters': 0,
            'file_size_mb': os.path.getsize(path) // (1024 * 1024),
            'quantization': 'unknown',
            'context_length': 2048,
        }


def parse_pytorch(path: str) -> dict:
    """
    Parse PyTorch model (usually .bin) with config.json.
    """
    config_path = pathlib.Path(path).with_name('config.json')
    if config_path.exists():
        with open(config_path, 'r') as cf:
            config = json.load(cf)
        
        arch = config.get('architectures', ['unknown'])[0]
        n_layers = config.get('num_hidden_layers', 0)
        hidden = config.get('hidden_size', 0)
        ctx = config.get('max_position_embeddings', 2048)
        n_params = config.get('num_parameters', 0)
        vocab = config.get('vocab_size', 32000)
        
        if n_params == 0 and n_layers and hidden:
            n_params = int(n_layers * (12 * hidden * hidden) + vocab * hidden)
        
        file_size_mb = os.path.getsize(path) // (1024 * 1024)
        return {
            'format': 'pytorch',
            'architecture': arch,
            'num_layers': n_layers,
            'embedding_length': hidden,
            'num_parameters': n_params,
            'file_size_mb': file_size_mb,
            'quantization': 'unknown',
            'context_length': ctx,
        }
    else:
        return {
            'format': 'pytorch',
            'architecture': 'unknown',
            'num_layers': 0,
            'embedding_length': 0,
            'num_parameters': 0,
            'file_size_mb': os.path.getsize(path) // (1024 * 1024),
            'quantization': 'unknown',
            'context_length': 2048,
        }


def parse_onnx(path: str) -> dict:
    """
    Parse ONNX model metadata (limited).
    """
    if onnx is None:
        raise RuntimeError("onnx module not available")
    
    model = onnx.load(path)
    file_size_mb = os.path.getsize(path) // (1024 * 1024)
    
    # Try to extract opset and producer info
    opset = None
    if model.opset_import:
        opset = model.opset_import[0].version if model.opset_import else None
    
    return {
        'format': 'onnx',
        'architecture': 'unknown',
        'num_layers': 0,
        'embedding_length': 0,
        'num_parameters': 0,
        'file_size_mb': file_size_mb,
        'quantization': 'unknown',
        'context_length': 2048,
        'opset_version': opset,
    }


def fallback_parse(path: str) -> dict:
    """
    Fallback when format is unknown or parsing fails.
    """
    file_size_mb = os.path.getsize(path) // (1024 * 1024)
    return {
        'format': 'unknown',
        'architecture': 'unknown',
        'num_layers': 0,
        'embedding_length': 0,
        'num_parameters': 0,
        'file_size_mb': file_size_mb,
        'quantization': 'unknown',
        'context_length': 2048,
    }


def get_size_label(num_parameters: int) -> str:
    """
    Generate human-readable size label based on parameter count.
    """
    if num_parameters == 0:
        return 'unknown'
    
    billions = num_parameters / 1e9
    if billions < 1:
        return f"{int(num_parameters / 1e6)}M"
    elif billions < 10:
        return f"{billions:.1f}B"
    else:
        return f"{int(billions)}B"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No model path provided"}))
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(json.dumps({"error": f"File not found: {path}"}))
        sys.exit(1)

    fmt = detect_format(path)
    
    try:
        if fmt == 'gguf':
            result = parse_gguf(path)
        elif fmt == 'safetensors':
            result = parse_safetensors(path)
        elif fmt == 'pytorch':
            result = parse_pytorch(path)
        elif fmt == 'onnx':
            result = parse_onnx(path)
        else:
            result = fallback_parse(path)
    except Exception as e:
        # If parsing fails, return a fallback with error info
        result = fallback_parse(path)
        result['parse_error'] = str(e)

    # Add size_label for compatibility with existing entrypoint.sh
    result['size_label'] = get_size_label(result.get('num_parameters', 0))

    print(json.dumps(result))


if __name__ == "__main__":
    main()
