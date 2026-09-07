#!/usr/bin/env python3
"""
Universal converter for any HuggingFace model to GGUF.
Auto-detects model type and runs convert_hf_to_gguf.py with proper arguments.
"""
import os
import sys
import subprocess
import json
import argparse
from pathlib import Path

def detect_model_type(model_path):
    config_path = Path(model_path) / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        arch = config.get("architectures", [""])[0].lower()
        if "llama" in arch:
            return "llama"
        elif "mistral" in arch:
            return "mistral"
        elif "falcon" in arch:
            return "falcon"
        elif "gpt2" in arch:
            return "gpt2"
        elif "bert" in arch:
            return "bert"
        elif "bloom" in arch:
            return "bloom"
        elif "qwen" in arch:
            return "qwen"
    # Fallback: try to guess from parent directory name
    model_name = Path(model_path).name.lower()
    for known in ["llama", "mistral", "falcon", "gpt2", "bert", "bloom", "qwen"]:
        if known in model_name:
            return known
    return "llama"  # default

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--outfile", required=True)
    args = parser.parse_args()

    model_path = args.model_path
    outfile = args.outfile

    if os.path.isfile(model_path):
        parent_dir = os.path.dirname(model_path)
        if os.path.isdir(parent_dir) and os.path.exists(os.path.join(parent_dir, "config.json")):
            model_type = detect_model_type(parent_dir)
        else:
            model_type = "llama"
    else:
        model_type = detect_model_type(model_path)

    cmd = [
        "python3", "convert_hf_to_gguf.py",
        "--model-type", model_type,
        "--outfile", outfile,
        model_path
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
